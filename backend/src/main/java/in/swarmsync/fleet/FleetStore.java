package in.swarmsync.fleet;

import org.springframework.stereotype.Component;

/** Latest live snapshot + latest end-of-run report (kept as raw JSON strings). */
@Component
public class FleetStore {
    private volatile String state;
    private volatile String report;
    public String getState() { return state; }
    public void setState(String s) { this.state = s; }
    public String getReport() { return report; }
    public void setReport(String r) { this.report = r; }
}
