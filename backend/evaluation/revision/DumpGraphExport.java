import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.neo4j.dbms.api.EnterpriseDatabaseManagementServiceBuilder;
import com.neo4j.configuration.OnlineBackupSettings;
import com.neo4j.configuration.ClusterSettings;
import com.neo4j.configuration.RaftSettings;
import org.neo4j.configuration.helpers.SocketAddress;
import org.neo4j.configuration.GraphDatabaseSettings;
import org.neo4j.configuration.connectors.BoltConnector;
import org.neo4j.configuration.connectors.HttpConnector;
import org.neo4j.configuration.connectors.HttpsConnector;
import org.neo4j.dbms.api.DatabaseManagementService;
import org.neo4j.graphdb.GraphDatabaseService;
import org.neo4j.graphdb.Result;
import org.neo4j.graphdb.Transaction;
import java.lang.reflect.Array;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Export a restored workspace copy with client/backup connectors disabled. */
public class DumpGraphExport {
    static Object normalize(Object value) {
        if (value == null || value instanceof String || value instanceof Number || value instanceof Boolean) return value;
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> output = new LinkedHashMap<>();
            map.forEach((key, item) -> output.put(key.toString(), normalize(item)));
            return output;
        }
        if (value instanceof Iterable<?> items) {
            List<Object> output = new ArrayList<>();
            items.forEach(item -> output.add(normalize(item)));
            return output;
        }
        if (value.getClass().isArray()) {
            List<Object> output = new ArrayList<>();
            for (int i = 0; i < Array.getLength(value); i++) output.add(normalize(Array.get(value, i)));
            return output;
        }
        return value.toString();
    }

    static List<Object> read(Transaction tx, String query) {
        List<Object> output = new ArrayList<>();
        try (Result result = tx.execute(query)) {
            while (result.hasNext()) output.add(normalize(result.next()));
        }
        return output;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("workspace-home output-json original-dump");
        Path home = Path.of(args[0]).toRealPath();
        Path output = Path.of(args[1]).toAbsolutePath().normalize();
        Path dump = Path.of(args[2]).toRealPath();
        if (!Files.isRegularFile(home.resolve(".revision-dump-copy"))) {
            throw new IllegalArgumentException("Refusing to open a database without the isolated-copy marker");
        }
        if (!output.startsWith(home)) throw new IllegalArgumentException("Export must stay inside isolated workspace home");
        if (Files.exists(output)) throw new IllegalArgumentException("Refusing to overwrite an existing snapshot");
        DatabaseManagementService service = new EnterpriseDatabaseManagementServiceBuilder(home)
            .setConfig(GraphDatabaseSettings.pagecache_memory, 134217728L)
            .setConfig(BoltConnector.enabled, false)
            .setConfig(HttpConnector.enabled, false)
            .setConfig(HttpsConnector.enabled, false)
            .setConfig(OnlineBackupSettings.online_backup_enabled, false)
            .setConfig(ClusterSettings.cluster_listen_address, new SocketAddress("127.0.0.1", 0))
            .setConfig(RaftSettings.raft_listen_address, new SocketAddress("127.0.0.1", 0))
            .build();
        try {
            long deadline = System.nanoTime() + 60_000_000_000L;
            while (!service.listDatabases().contains("neo4j")) {
                if (System.nanoTime() >= deadline) throw new IllegalStateException("Restored database was not registered");
                Thread.sleep(100);
            }
            GraphDatabaseService database = service.database("neo4j");
            if (!database.isAvailable(60000)) throw new IllegalStateException("Restored database did not become available");
            Map<String, Object> snapshot = new LinkedHashMap<>();
            snapshot.put("schema_version", 1);
            snapshot.put("exported_at", Instant.now().toString());
            snapshot.put("provenance", "Exported from isolated restored author-supplied dump; submission-time graph identity unconfirmed");
            snapshot.put("original_dump_name", dump.getFileName().toString());
            snapshot.put("original_dump_sha256", HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(dump))));
            try (Transaction tx = database.beginTx()) {
                snapshot.put("nodes", read(tx, "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties ORDER BY id"));
                snapshot.put("edges", read(tx, "MATCH (s)-[r]->(t) RETURN elementId(r) AS id, elementId(s) AS source, elementId(t) AS target, type(r) AS type, properties(r) AS properties ORDER BY id"));
            }
            new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT).writeValue(output.toFile(), snapshot);
            System.out.println("EXPORTED nodes=" + ((List<?>) snapshot.get("nodes")).size() + " edges=" + ((List<?>) snapshot.get("edges")).size());
        } finally {
            service.shutdown();
        }
    }
}
