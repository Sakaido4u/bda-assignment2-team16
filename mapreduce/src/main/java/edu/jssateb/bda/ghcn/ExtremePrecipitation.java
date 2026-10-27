package edu.jssateb.bda.ghcn;

import java.io.IOException;

import org.apache.hadoop.conf.Configured;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.IntWritable;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;
import org.apache.hadoop.mapreduce.lib.reduce.IntSumReducer;
import org.apache.hadoop.util.Tool;

/**
 * Job 2: number of extreme-precipitation days per station.
 * A day is "extreme" when PRCP >= ghcn.prcp.threshold (tenths of mm; default 500 = 50 mm/day,
 * a commonly used heavy-rainfall threshold; pass -D ghcn.prcp.threshold=... to change it).
 */
public class ExtremePrecipitation extends Configured implements Tool {

    public enum Extreme { EXTREME_DAYS, PRCP_READINGS }

    public static class PrcpMapper extends Mapper<LongWritable, Text, Text, IntWritable> {
        private static final IntWritable ONE = new IntWritable(1);
        private final GhcnRecord rec = new GhcnRecord();
        private final Text station = new Text();
        private int threshold;

        @Override
        protected void setup(Context ctx) {
            threshold = ctx.getConfiguration().getInt("ghcn.prcp.threshold", 500);
        }

        @Override
        protected void map(LongWritable key, Text line, Context ctx) throws IOException, InterruptedException {
            if (!rec.parse(line.toString())) {
                ctx.getCounter(GhcnRecord.Quality.MALFORMED).increment(1);
                return;
            }
            if (!"PRCP".equals(rec.element)) {
                ctx.getCounter(GhcnRecord.Quality.OTHER_ELEMENT).increment(1);
                return;
            }
            if (rec.qcFailed) {
                ctx.getCounter(GhcnRecord.Quality.QC_FAILED).increment(1);
                return;
            }
            if (rec.isMissing()) {
                ctx.getCounter(GhcnRecord.Quality.MISSING_VALUE).increment(1);
                return;
            }
            ctx.getCounter(GhcnRecord.Quality.VALID).increment(1);
            ctx.getCounter(Extreme.PRCP_READINGS).increment(1);
            if (rec.value >= threshold) {
                ctx.getCounter(Extreme.EXTREME_DAYS).increment(1);
                station.set(rec.stationId);
                ctx.write(station, ONE);
            }
        }
    }

    @Override
    public int run(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: extreme-precip <input> <output>");
            return 2;
        }
        Job job = Job.getInstance(getConf(), "GHCN Job2 - extreme precipitation days per station (Java)");
        job.setJarByClass(ExtremePrecipitation.class);
        job.setMapperClass(PrcpMapper.class);
        job.setCombinerClass(IntSumReducer.class);
        job.setReducerClass(IntSumReducer.class);
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(IntWritable.class);
        job.setNumReduceTasks(getConf().getInt("ghcn.reducers", 2));
        FileInputFormat.addInputPath(job, new Path(args[0]));
        Path out = new Path(args[1]);
        FileSystem.get(getConf()).delete(out, true);
        FileOutputFormat.setOutputPath(job, out);
        return job.waitForCompletion(true) ? 0 : 1;
    }
}
