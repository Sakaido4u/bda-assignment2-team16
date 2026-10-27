package edu.jssateb.bda.ghcn;

import java.util.Arrays;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.util.ToolRunner;

/**
 * Entry point:  hadoop jar ghcn-mapreduce.jar <country-temp|extreme-precip> [-D k=v] <in> <out>
 */
public final class GhcnJobs {
    private GhcnJobs() { }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: hadoop jar ghcn-mapreduce.jar <country-temp|extreme-precip> [-D k=v] <input> <output>");
            System.exit(2);
        }
        String[] rest = Arrays.copyOfRange(args, 1, args.length);
        int rc;
        switch (args[0]) {
            case "country-temp":
                rc = ToolRunner.run(new Configuration(), new CountryYearTemperature(), rest);
                break;
            case "extreme-precip":
                rc = ToolRunner.run(new Configuration(), new ExtremePrecipitation(), rest);
                break;
            default:
                System.err.println("unknown job: " + args[0]);
                rc = 2;
        }
        System.exit(rc);
    }
}
