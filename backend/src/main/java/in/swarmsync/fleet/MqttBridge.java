package in.swarmsync.fleet;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.annotation.PostConstruct;
import org.eclipse.paho.client.mqttv3.*;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;

/** Listens (read-only) to the local MQTT broker's dashboard feed and fans it out to REST/WebSocket/DB. */
@Component
public class MqttBridge {
    private static final Logger log = LoggerFactory.getLogger(MqttBridge.class);
    private final FleetStore store;
    private final LiveSocketHandler ws;
    private final TickLogRepository repo;
    private final ObjectMapper om = new ObjectMapper();

    @Value("${swarm.mqtt.url}")
    private String url;

    public MqttBridge(FleetStore store, LiveSocketHandler ws, TickLogRepository repo) {
        this.store = store; this.ws = ws; this.repo = repo;
    }

    @PostConstruct
    void start() {
        Thread t = new Thread(this::connectLoop, "mqtt-connect");
        t.setDaemon(true);
        t.start();
    }

    private void connectLoop() {
        while (true) {
            try {
                MqttClient c = new MqttClient(url, "fleet-backend", new MemoryPersistence());
                MqttConnectOptions o = new MqttConnectOptions();
                o.setAutomaticReconnect(true);
                o.setCleanSession(true);
                c.setCallback(new MqttCallbackExtended() {
                    @Override public void connectComplete(boolean reconnect, String uri) {
                        try { c.subscribe("swarm/state", 1); c.subscribe("swarm/report", 1); }
                        catch (MqttException e) { log.error("subscribe failed", e); }
                    }
                    @Override public void connectionLost(Throwable cause) { log.warn("MQTT connection lost"); }
                    @Override public void messageArrived(String topic, MqttMessage msg) {
                        handle(topic, new String(msg.getPayload(), StandardCharsets.UTF_8));
                    }
                    @Override public void deliveryComplete(IMqttDeliveryToken token) { }
                });
                c.connect(o);
                log.info("Connected to MQTT broker {}", url);
                return;
            } catch (Exception e) {
                log.warn("Broker not reachable ({}), retrying in 2s", e.getMessage());
                try { Thread.sleep(2000); } catch (InterruptedException ie) { return; }
            }
        }
    }

    private void handle(String topic, String json) {
        try {
            if (topic.equals("swarm/state")) {
                store.setState(json);
                ws.broadcast(json);
                JsonNode n = om.readTree(json);
                int tick = n.get("t").asInt();
                if (tick % 5 == 0) {
                    ((ObjectNode) n).remove("map");
                    TickLog l = new TickLog();
                    l.tick = tick;
                    l.collisions = n.get("collisions").asInt();
                    l.done = n.get("done").asInt();
                    l.total = n.get("total").asInt();
                    l.payload = om.writeValueAsString(n);
                    repo.save(l);
                }
            } else if (topic.equals("swarm/report")) {
                store.setReport(json);
                ws.broadcast("{\"report\":" + json + "}");
            }
        } catch (Exception e) { log.error("bad message on {}", topic, e); }
    }
}
