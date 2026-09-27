import com.fasterxml.jackson.databind.ObjectMapper;
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
import org.neo4j.graphdb.Transaction;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

/** Password-protected loopback Bolt service for a separately imported graph. */
public class LocalGraphServer {
    static DatabaseManagementService open(Path home, boolean serve, int port) {
        return new EnterpriseDatabaseManagementServiceBuilder(home)
            .setConfig(GraphDatabaseSettings.pagecache_memory, 134217728L)
            .setConfig(GraphDatabaseSettings.auth_enabled, true)
            .setConfig(GraphDatabaseSettings.routing_enabled, false)
            .setConfig(BoltConnector.enabled, serve)
            .setConfig(BoltConnector.listen_address, new SocketAddress("127.0.0.1", port))
            .setConfig(BoltConnector.advertised_address, new SocketAddress("127.0.0.1", port))
            .setConfig(HttpConnector.enabled, false)
            .setConfig(HttpsConnector.enabled, false)
            .setConfig(OnlineBackupSettings.online_backup_enabled, false)
            .setConfig(ClusterSettings.cluster_listen_address, new SocketAddress("127.0.0.1", 0))
            .setConfig(RaftSettings.raft_listen_address, new SocketAddress("127.0.0.1", 0)).build();
    }
    static void waitForGraph(DatabaseManagementService service) throws Exception {
        long deadline = System.nanoTime() + 60_000_000_000L;
        while (!service.listDatabases().contains("neo4j")) {
            if (System.nanoTime() > deadline) throw new IllegalStateException("Database registration timed out");
            Thread.sleep(100);
        }
        if (!service.database("neo4j").isAvailable(60000)) throw new IllegalStateException("Graph unavailable");
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("Expected isolated import home");
        Path home = Path.of(args[0]).toRealPath();
        if (!Files.isRegularFile(home.resolve(".revision-snapshot-import"))) throw new IllegalArgumentException("Missing isolated import marker");
        ObjectMapper mapper = new ObjectMapper();
        Map<?, ?> credentials = mapper.readValue(home.resolve("connection.private.json").toFile(), Map.class);
        String password = (String) credentials.get("password");
        int port = ((Number) credentials.get("port")).intValue();
        Path initialized = home.resolve("run/auth-initialized");
        if (!Files.exists(initialized)) {
            DatabaseManagementService bootstrap = open(home, false, port);
            try {
                waitForGraph(bootstrap);
                try (Transaction tx = bootstrap.database("system").beginTx()) {
                    tx.execute("ALTER USER neo4j SET PASSWORD $password CHANGE NOT REQUIRED", Map.of("password", password)).close();
                    tx.commit();
                }
                Files.writeString(initialized, "Credentials initialized for this isolated copy.\n");
            } finally { bootstrap.shutdown(); }
        }
        DatabaseManagementService service = open(home, true, port);
        long started = System.currentTimeMillis();
        Path status = home.resolve("server_status.json"), stop = home.resolve("run/STOP.request");
        Runtime.getRuntime().addShutdownHook(new Thread(service::shutdown));
        try {
            waitForGraph(service);
            mapper.writeValue(status.toFile(), Map.of("state", "running", "pid", ProcessHandle.current().pid(),
                "bolt_uri", "bolt://127.0.0.1:" + port, "started_epoch_ms", started));
            System.out.println("LOCAL_GRAPH_READY bolt://127.0.0.1:" + port);
            while (!Files.exists(stop) || Files.getLastModifiedTime(stop).toMillis() < started) Thread.sleep(500);
        } finally {
            service.shutdown();
            mapper.writeValue(status.toFile(), Map.of("state", "stopped", "pid", ProcessHandle.current().pid()));
        }
    }
}
