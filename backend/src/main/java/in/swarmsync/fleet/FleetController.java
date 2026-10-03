package in.swarmsync.fleet;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/api")
@CrossOrigin
public class FleetController {
    private final FleetStore store;
    private final TickLogRepository repo;

    public FleetController(FleetStore store, TickLogRepository repo) { this.store = store; this.repo = repo; }

    @GetMapping(value = "/state", produces = "application/json")
    public ResponseEntity<String> state() {
        return store.getState() == null ? ResponseEntity.noContent().build() : ResponseEntity.ok(store.getState());
    }

    @GetMapping(value = "/report", produces = "application/json")
    public ResponseEntity<String> report() {
        return store.getReport() == null ? ResponseEntity.noContent().build() : ResponseEntity.ok(store.getReport());
    }

    @GetMapping("/history")
    public List<TickLog> history() { return repo.findTop200ByOrderByIdDesc(); }
}
