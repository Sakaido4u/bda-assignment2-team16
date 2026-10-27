package edu.jssateb.bda.ghcn;

/**
 * Parses one line of a GHCN-Daily by_year CSV file:
 * ID, DATE(YYYYMMDD), ELEMENT, DATA_VALUE, M_FLAG, Q_FLAG, S_FLAG, OBS_TIME
 */
public final class GhcnRecord {

    /** Custom counters shown in the job output and in the JobHistory UI. */
    public enum Quality { VALID, MALFORMED, QC_FAILED, MISSING_VALUE, OTHER_ELEMENT }

    public String stationId;
    public String countryCode;
    public String year;
    public String month;
    public String element;
    public int value;
    public boolean qcFailed;

    /** @return true if the line had the expected shape and a numeric value */
    public boolean parse(String line) {
        String[] p = line.split(",", -1);
        if (p.length < 7 || p[0].length() != 11 || p[1].length() != 8) {
            return false;
        }
        stationId = p[0];
        countryCode = p[0].substring(0, 2);
        year = p[1].substring(0, 4);
        month = p[1].substring(4, 6);
        element = p[2];
        qcFailed = !p[5].trim().isEmpty();      // non-empty Q_FLAG = failed quality control
        if (p[3].isEmpty()) {
            return false;
        }
        try {
            value = Integer.parseInt(p[3].trim());
        } catch (NumberFormatException e) {
            return false;
        }
        return true;
    }

    /** -9999 is the documented "missing" sentinel. */
    public boolean isMissing() {
        return value == -9999;
    }
}
