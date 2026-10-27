package edu.jssateb.bda.ghcn;

import java.io.DataInput;
import java.io.DataOutput;
import java.io.IOException;

import org.apache.hadoop.io.Writable;

/**
 * Partial aggregate for temperatures: sum and count of TMAX and TMIN (tenths of deg C).
 * Because sum and count are both additive, the same object can be merged in the
 * Combiner and in the Reducer - averaging averages would be wrong, this is not.
 */
public class TempStatsWritable implements Writable {

    private long tmaxSum;
    private long tmaxCount;
    private long tminSum;
    private long tminCount;

    public TempStatsWritable() { }

    public void set(long tmaxSum, long tmaxCount, long tminSum, long tminCount) {
        this.tmaxSum = tmaxSum;
        this.tmaxCount = tmaxCount;
        this.tminSum = tminSum;
        this.tminCount = tminCount;
    }

    public void merge(TempStatsWritable o) {
        tmaxSum += o.tmaxSum;
        tmaxCount += o.tmaxCount;
        tminSum += o.tminSum;
        tminCount += o.tminCount;
    }

    public void clear() { set(0, 0, 0, 0); }

    public long getTmaxCount() { return tmaxCount; }
    public long getTminCount() { return tminCount; }

    /** average in deg C (values are stored in tenths of a degree) */
    public double avgTmaxC() { return tmaxCount == 0 ? Double.NaN : tmaxSum / 10.0 / tmaxCount; }
    public double avgTminC() { return tminCount == 0 ? Double.NaN : tminSum / 10.0 / tminCount; }

    @Override
    public void write(DataOutput out) throws IOException {
        out.writeLong(tmaxSum);
        out.writeLong(tmaxCount);
        out.writeLong(tminSum);
        out.writeLong(tminCount);
    }

    @Override
    public void readFields(DataInput in) throws IOException {
        tmaxSum = in.readLong();
        tmaxCount = in.readLong();
        tminSum = in.readLong();
        tminCount = in.readLong();
    }
}
