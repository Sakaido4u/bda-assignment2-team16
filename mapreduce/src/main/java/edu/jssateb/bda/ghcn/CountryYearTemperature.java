package edu.jssateb.bda.ghcn;

import java.io.IOException;

import org.apache.hadoop.conf.Configured;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;
import org.apache.hadoop.util.Tool;

/**
 * Job 1: average yearly TMAX and TMIN per country.
 *   map:     line -> (country \t year, TempStats{one reading})
 *   combine: merge partial sums/counts on the map side (cuts shuffle volume)
 *   reduce:  merge, then output avg TMAX, avg TMIN (deg C) and reading counts
 */
public class CountryYearTemperature extends Configured implements Tool {

    public static class TempMapper extends Mapper<LongWritable, Text, Text, TempStatsWritable> {
        private final GhcnRecord rec = new GhcnRecord();
        private final Text outKey = new Text();
        private final TempStatsWritable outVal = new TempStatsWritable();

        @Override
        protected void map(LongWritable key, Text line, Context ctx) throws IOException, InterruptedException {
            if (!rec.parse(line.toString())) {
                ctx.getCounter(GhcnRecord.Quality.MALFORMED).increment(1);
                return;
            }
            boolean isMax = "TMAX".equals(rec.element);
            boolean isMin = "TMIN".equals(rec.element);
            if (!isMax && !isMin) {
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
            outKey.set(rec.countryCode + "\t" + rec.year);
            if (isMax) {
                outVal.set(rec.value, 1, 0, 0);
            } else {
                outVal.set(0, 0, rec.value, 1);
            }
            ctx.write(outKey, outVal);
        }
    }

    public static class TempCombiner extends Reducer<Text, TempStatsWritable, Text, TempStatsWritable> {
        private final TempStatsWritable acc = new TempStatsWritable();

        @Override
        protected void reduce(Text key, Iterable<TempStatsWritable> vals, Context ctx) throws IOException, InterruptedException {
            acc.clear();
            for (TempStatsWritable v : vals) {
                acc.merge(v);
            }
            ctx.write(key, acc);
        }
    }

    public static class TempReducer extends Reducer<Text, TempStatsWritable, Text, Text> {
        private final TempStatsWritable acc = new TempStatsWritable();
        private final Text out = new Text();

        @Override
        protected void reduce(Text key, Iterable<TempStatsWritable> vals, Context ctx) throws IOException, InterruptedException {
            acc.clear();
            for (TempStatsWritable v : vals) {
                acc.merge(v);
            }
            out.set(String.format("%.2f\t%.2f\t%d\t%d",
                    acc.avgTmaxC(), acc.avgTminC(), acc.getTmaxCount(), acc.getTminCount()));
            ctx.write(key, out);
        }
    }

    @Override
    public int run(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: country-temp <input> <output>");
            return 2;
        }
        Job job = Job.getInstance(getConf(), "GHCN Job1 - yearly avg TMAX/TMIN per country (Java)");
        job.setJarByClass(CountryYearTemperature.class);
        job.setMapperClass(TempMapper.class);
        job.setCombinerClass(TempCombiner.class);
        job.setReducerClass(TempReducer.class);
        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(TempStatsWritable.class);
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(Text.class);
        job.setNumReduceTasks(getConf().getInt("ghcn.reducers", 2));
        FileInputFormat.addInputPath(job, new Path(args[0]));
        Path out = new Path(args[1]);
        FileSystem.get(getConf()).delete(out, true);
        FileOutputFormat.setOutputPath(job, out);
        return job.waitForCompletion(true) ? 0 : 1;
    }
}
