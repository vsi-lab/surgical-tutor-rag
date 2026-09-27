import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.neo4j.dbms.api.EnterpriseDatabaseManagementServiceBuilder;
import com.neo4j.configuration.ClusterSettings;
import com.neo4j.configuration.OnlineBackupSettings;
import com.neo4j.configuration.RaftSettings;
import org.neo4j.configuration.GraphDatabaseSettings;
import org.neo4j.configuration.connectors.BoltConnector;
import org.neo4j.configuration.connectors.HttpConnector;
import org.neo4j.configuration.connectors.HttpsConnector;
import org.neo4j.configuration.helpers.SocketAddress;
import org.neo4j.dbms.api.DatabaseManagementService;
import org.neo4j.graphdb.Entity;
import org.neo4j.graphdb.GraphDatabaseService;
import org.neo4j.graphdb.Label;
import org.neo4j.graphdb.Node;
import org.neo4j.graphdb.Relationship;
import org.neo4j.graphdb.RelationshipType;
import org.neo4j.graphdb.Result;
import org.neo4j.graphdb.Transaction;
import java.lang.reflect.Array;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Imports only a new, marked workspace database and validates committed readback. */
public class SnapshotGraphImport {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String PREFIX = "_revision_";
    private static final String ID = PREFIX + "snapshot_id";
    private static final String INDEX = PREFIX + "record_index";
    private static final String RECORD = PREFIX + "record_json";
    private static final String ENCODED = PREFIX + "json_encoded_keys";

    private static String text(JsonNode object, String key) {
        JsonNode value = object.get(key);
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw new IllegalArgumentException("Expected nonempty string field: " + key);
        }
        return value.textValue();
    }

    private static String edgeId(JsonNode edge, int index) {
        return edge.has("id") ? text(edge, "id") : "_revision_missing_edge_" + index;
    }

    private static void validateSnapshot(JsonNode snapshot) {
        if (!snapshot.isObject() || !snapshot.path("nodes").isArray() || !snapshot.path("edges").isArray()) {
            throw new IllegalArgumentException("Snapshot needs nodes and edges arrays");
        }
        Set<String> ids = new HashSet<>();
        for (JsonNode node : snapshot.get("nodes")) {
            if (!ids.add(text(node, "id"))) throw new IllegalArgumentException("Duplicate node ID");
            JsonNode labels = node.path("labels");
            if (!labels.isMissingNode() && !labels.isArray()) throw new IllegalArgumentException("Invalid labels");
            Set<String> distinct = new HashSet<>();
            for (JsonNode label : labels) {
                if (!label.isTextual() || label.textValue().isBlank() || !distinct.add(label.textValue())) {
                    throw new IllegalArgumentException("Labels must be unique nonempty strings");
                }
            }
            validateProperties(node);
        }
        Set<String> edgeIds = new HashSet<>();
        int index = 0;
        for (JsonNode edge : snapshot.get("edges")) {
            if (!ids.contains(text(edge, "source")) || !ids.contains(text(edge, "target"))) {
                throw new IllegalArgumentException("Dangling edge endpoint");
            }
            text(edge, "type");
            if (!edgeIds.add(edgeId(edge, index++))) throw new IllegalArgumentException("Duplicate edge ID");
            validateProperties(edge);
        }
    }

    private static void validateProperties(JsonNode record) {
        JsonNode properties = record.path("properties");
        if (!properties.isMissingNode() && !properties.isObject()) throw new IllegalArgumentException("Properties must be an object");
        properties.fieldNames().forEachRemaining(key -> {
            if (key.isEmpty() || key.startsWith(PREFIX)) throw new IllegalArgumentException("Reserved or empty property key");
        });
    }

    /** Return a native Neo4j value, or null to require explicit JSON encoding. */
    private static Object nativeValue(JsonNode value) {
        if (value.isTextual()) return value.textValue();
        if (value.isBoolean()) return value.booleanValue();
        if (value.isIntegralNumber() && value.canConvertToLong()) return value.longValue();
        if (value.isFloatingPointNumber() && Double.isFinite(value.doubleValue())) return value.doubleValue();
        if (!value.isArray() || value.isEmpty()) return null;
        int size = value.size();
        boolean strings = true, bools = true, integers = true, decimals = true;
        for (JsonNode item : value) {
            strings &= item.isTextual();
            bools &= item.isBoolean();
            integers &= item.isIntegralNumber() && item.canConvertToLong();
            decimals &= item.isFloatingPointNumber() && Double.isFinite(item.doubleValue());
        }
        if (strings) {
            String[] result = new String[size];
            for (int i = 0; i < size; i++) result[i] = value.get(i).textValue();
            return result;
        }
        if (bools) {
            boolean[] result = new boolean[size];
            for (int i = 0; i < size; i++) result[i] = value.get(i).booleanValue();
            return result;
        }
        if (integers) {
            long[] result = new long[size];
            for (int i = 0; i < size; i++) result[i] = value.get(i).longValue();
            return result;
        }
        if (decimals) {
            double[] result = new double[size];
            for (int i = 0; i < size; i++) result[i] = value.get(i).doubleValue();
            return result;
        }
        return null;
    }

    private static Map<String, Object> mappedProperties(JsonNode record, String externalId, int index) throws Exception {
        Map<String, Object> output = new LinkedHashMap<>();
        List<String> encoded = new ArrayList<>();
        var fields = record.path("properties").fields();
        while (fields.hasNext()) {
            var field = fields.next();
            Object value = nativeValue(field.getValue());
            if (value == null) {
                value = JSON.writeValueAsString(field.getValue());
                encoded.add(field.getKey());
            }
            output.put(field.getKey(), value);
        }
        output.put(ID, externalId);
        output.put(INDEX, (long) index);
        output.put(RECORD, JSON.writeValueAsString(record));
        output.put(ENCODED, encoded.toArray(String[]::new));
        return output;
    }

    private static void setProperties(Entity entity, JsonNode record, String id, int index) throws Exception {
        for (var field : mappedProperties(record, id, index).entrySet()) entity.setProperty(field.getKey(), field.getValue());
    }

    private static boolean equalValue(Object left, Object right) {
        if (left != null && right != null && left.getClass().isArray() && right.getClass().isArray()) {
            if (Array.getLength(left) != Array.getLength(right)) return false;
            for (int i = 0; i < Array.getLength(left); i++) {
                if (!equalValue(Array.get(left, i), Array.get(right, i))) return false;
            }
            return true;
        }
        return java.util.Objects.equals(left, right);
    }

    private static JsonNode validateEntity(Entity entity, JsonNode expected, String id, int index) throws Exception {
        Map<String, Object> actual = entity.getAllProperties();
        Map<String, Object> desired = mappedProperties(expected, id, index);
        if (!actual.keySet().equals(desired.keySet())) throw new IllegalStateException("Property key mismatch at record " + index);
        for (String key : desired.keySet()) {
            if (!equalValue(actual.get(key), desired.get(key))) {
                throw new IllegalStateException("Property value mismatch at record " + index + " key " + key);
            }
        }
        JsonNode recovered = JSON.readTree((String) actual.get(RECORD));
        if (!recovered.equals(expected)) throw new IllegalStateException("Lossless record mismatch");
        return recovered;
    }

    private static void createGraph(GraphDatabaseService database, JsonNode snapshot) throws Exception {
        try (Transaction tx = database.beginTx()) {
            try (Result existing = tx.execute("MATCH (n) RETURN count(n) AS n")) {
                if (((Number) existing.next().get("n")).longValue() != 0) {
                    throw new IllegalStateException("Refusing to import into a nonempty database");
                }
            }
            Map<String, Node> nodes = new HashMap<>();
            int index = 0;
            for (JsonNode record : snapshot.get("nodes")) {
                List<Label> labels = new ArrayList<>();
                record.path("labels").forEach(label -> labels.add(Label.label(label.textValue())));
                Node node = tx.createNode(labels.toArray(Label[]::new));
                String id = text(record, "id");
                setProperties(node, record, id, index++);
                nodes.put(id, node);
            }
            index = 0;
            for (JsonNode record : snapshot.get("edges")) {
                Relationship relationship = nodes.get(text(record, "source")).createRelationshipTo(
                    nodes.get(text(record, "target")), RelationshipType.withName(text(record, "type")));
                setProperties(relationship, record, edgeId(record, index), index);
                index++;
            }
            tx.commit();
        }
    }

    private static ObjectNode readAndValidate(GraphDatabaseService database, JsonNode snapshot) throws Exception {
        ObjectNode recovered = ((ObjectNode) snapshot).deepCopy();
        ArrayNode nodes = JSON.createArrayNode(), edges = JSON.createArrayNode();
        try (Transaction tx = database.beginTx()) {
            int index = 0;
            try (Result result = tx.execute("MATCH (n) RETURN n ORDER BY n._revision_record_index")) {
                while (result.hasNext()) {
                    if (index >= snapshot.get("nodes").size()) throw new IllegalStateException("Excess nodes on readback");
                    Node node = (Node) result.next().get("n");
                    JsonNode expected = snapshot.get("nodes").get(index);
                    Set<String> expectedLabels = new HashSet<>(), actualLabels = new HashSet<>();
                    expected.path("labels").forEach(label -> expectedLabels.add(label.textValue()));
                    node.getLabels().forEach(label -> actualLabels.add(label.name()));
                    if (!expectedLabels.equals(actualLabels)) throw new IllegalStateException("Node labels differ on readback");
                    nodes.add(validateEntity(node, expected, text(expected, "id"), index++));
                }
            }
            if (index != snapshot.get("nodes").size()) throw new IllegalStateException("Node count mismatch");
            index = 0;
            try (Result result = tx.execute("MATCH ()-[r]->() RETURN r ORDER BY r._revision_record_index")) {
                while (result.hasNext()) {
                    if (index >= snapshot.get("edges").size()) throw new IllegalStateException("Excess edges on readback");
                    Relationship relationship = (Relationship) result.next().get("r");
                    JsonNode expected = snapshot.get("edges").get(index);
                    if (!relationship.getType().name().equals(text(expected, "type")) ||
                        !relationship.getStartNode().getProperty(ID).equals(text(expected, "source")) ||
                        !relationship.getEndNode().getProperty(ID).equals(text(expected, "target"))) {
                        throw new IllegalStateException("Relationship endpoints or type differ on readback");
                    }
                    edges.add(validateEntity(relationship, expected, edgeId(expected, index), index));
                    index++;
                }
            }
            if (index != snapshot.get("edges").size()) throw new IllegalStateException("Relationship count mismatch");
        }
        recovered.set("nodes", nodes);
        recovered.set("edges", edges);
        if (!recovered.equals(snapshot)) throw new IllegalStateException("Snapshot content differs on readback");
        return recovered;
    }

    private static void writeNew(Path path, JsonNode value) throws Exception {
        Files.writeString(path, JSON.writerWithDefaultPrettyPrinter().writeValueAsString(value) + "\n", StandardOpenOption.CREATE_NEW);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("fresh-workspace-home input-snapshot-json");
        Path home = Path.of(args[0]).toRealPath();
        Path input = Path.of(args[1]).toRealPath();
        byte[] bytes = Files.readAllBytes(input);
        String checksum = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        Path marker = home.resolve(".revision-snapshot-import");
        if (!input.startsWith(home) || !Files.isRegularFile(marker) || !Files.readString(marker).strip().equals(checksum)) {
            throw new IllegalArgumentException("Input must belong to a freshly marked isolated import directory");
        }
        Path data = home.resolve("data");
        if (!Files.isDirectory(data) || !data.toRealPath().startsWith(home)) throw new IllegalArgumentException("Invalid isolated data directory");
        try (var contents = Files.list(data)) {
            if (contents.findAny().isPresent()) throw new IllegalArgumentException("Data directory is not empty; refusing to open existing database");
        }
        if (Files.exists(home.resolve("readback_snapshot.json")) || Files.exists(home.resolve("validation.json"))) {
            throw new IllegalArgumentException("Refusing to overwrite validation outputs");
        }
        JsonNode snapshot = JSON.readTree(bytes);
        validateSnapshot(snapshot);
        DatabaseManagementService service = new EnterpriseDatabaseManagementServiceBuilder(home)
            .setConfig(GraphDatabaseSettings.pagecache_memory, 134217728L)
            .setConfig(BoltConnector.enabled, false)
            .setConfig(HttpConnector.enabled, false)
            .setConfig(HttpsConnector.enabled, false)
            .setConfig(OnlineBackupSettings.online_backup_enabled, false)
            .setConfig(ClusterSettings.cluster_listen_address, new SocketAddress("127.0.0.1", 0))
            .setConfig(RaftSettings.raft_listen_address, new SocketAddress("127.0.0.1", 0))
            .build();
        ObjectNode recovered;
        try {
            long deadline = System.nanoTime() + 60_000_000_000L;
            while (!service.listDatabases().contains("neo4j")) {
                if (System.nanoTime() >= deadline) throw new IllegalStateException("New database was not registered");
                Thread.sleep(100);
            }
            GraphDatabaseService database = service.database("neo4j");
            if (!database.isAvailable(60000)) throw new IllegalStateException("New database unavailable");
            createGraph(database, snapshot);
            recovered = readAndValidate(database, snapshot);
        } finally {
            service.shutdown();
        }
        writeNew(home.resolve("readback_snapshot.json"), recovered);
        ObjectNode validation = JSON.createObjectNode();
        validation.put("status", "validated");
        validation.put("input_snapshot_sha256", checksum);
        validation.put("node_count", snapshot.get("nodes").size());
        validation.put("edge_count", snapshot.get("edges").size());
        validation.put("all_labels_endpoints_types_properties_match", true);
        validation.put("lossless_records_match", true);
        validation.put("database_shutdown_before_validation_output", true);
        validation.put("client_connectors_enabled", false);
        writeNew(home.resolve("validation.json"), validation);
        System.out.println("IMPORTED_AND_VALIDATED nodes=" + snapshot.get("nodes").size() + " edges=" + snapshot.get("edges").size());
    }
}
