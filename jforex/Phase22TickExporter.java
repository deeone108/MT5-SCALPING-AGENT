package jforex;

import com.dukascopy.api.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.*;

/** Research-data exporter: writes historical ticks and never submits orders. */
@RequiresFullAccess
public class Phase22TickExporter implements IStrategy {
    @Configurable("Instrument") public Instrument instrument = Instrument.EURUSD;
    @Configurable("Output CSV") public File outputFile = new File("EURUSD_20190107T000000Z_20190114T000000Z_JFOREX_TICKS.csv");
    @Configurable("Start UTC inclusive") public String startUtc = "2019-01-07 00:00:00.000";
    @Configurable("End UTC exclusive") public String endUtc = "2019-01-14 00:00:00.000";

    private BufferedWriter writer;
    private long start;
    private long end;
    private long sequence;

    public void onStart(IContext context) throws JFException {
        try {
            SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS");
            format.setLenient(false);
            format.setTimeZone(TimeZone.getTimeZone("UTC"));
            start = format.parse(startUtc).getTime();
            end = format.parse(endUtc).getTime();
            if (start >= end) throw new IllegalArgumentException("start must precede end");
            if (outputFile.exists()) throw new IOException("refusing to overwrite existing export: " + outputFile);
            writer = new BufferedWriter(new OutputStreamWriter(new FileOutputStream(outputFile), StandardCharsets.UTF_8));
            writer.write("timestamp_utc_ms,pair,bid,ask,bid_volume,ask_volume,source_sequence\n");
        } catch (Exception error) {
            throw new JFException("Could not initialize export: " + error.getMessage());
        }
    }

    public void onTick(Instrument tickInstrument, ITick tick) throws JFException {
        if (!instrument.equals(tickInstrument) || tick.getTime() < start || tick.getTime() >= end) return;
        try {
            writer.write(String.format(Locale.ROOT, "%d,%s,%.10f,%.10f,%.10f,%.10f,%d%n",
                tick.getTime(), instrument.name(), tick.getBid(), tick.getAsk(),
                tick.getBidVolume(), tick.getAskVolume(), sequence++));
        } catch (IOException error) {
            throw new JFException("Export write failed: " + error.getMessage());
        }
    }

    public void onStop() throws JFException {
        try { if (writer != null) writer.close(); }
        catch (IOException error) { throw new JFException("Export close failed: " + error.getMessage()); }
    }
    public void onAccount(IAccount account) {}
    public void onMessage(IMessage message) {}
    public void onBar(Instrument instrument, Period period, IBar askBar, IBar bidBar) {}
}
