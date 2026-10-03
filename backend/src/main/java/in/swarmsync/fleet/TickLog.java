package in.swarmsync.fleet;

import jakarta.persistence.*;
import java.time.Instant;

/** Historical log: one row every 5th tick (positions, battery, task status, collisions so far). */
@Entity
public class TickLog {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long id;
    public int tick;
    public int collisions;
    public int done;
    public int total;
    public Instant at = Instant.now();
    @Column(length = 20000)
    public String payload;
}
