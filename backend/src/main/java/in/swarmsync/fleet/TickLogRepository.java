package in.swarmsync.fleet;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface TickLogRepository extends JpaRepository<TickLog, Long> {
    List<TickLog> findTop200ByOrderByIdDesc();
}
