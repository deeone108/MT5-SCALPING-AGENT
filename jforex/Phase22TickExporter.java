package jforex;

import com.dukascopy.api.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.text.SimpleDateFormat;
import java.util.*;

/** Historical-tick file exporter. It has no engine, order, or position API. */
@RequiresFullAccess
public class Phase22TickExporter implements IStrategy {
    @Configurable("Mode (SINGLE_UNIT or YEAR_BATCH)") public String mode = "SINGLE_UNIT";
    @Configurable("Instrument") public Instrument instrument = Instrument.EURUSD;
    @Configurable("Single output CSV") public File outputFile = new File("EURUSD_20190107T000000Z_20190114T000000Z_JFOREX_TICKS.csv");
    @Configurable("Single start UTC inclusive") public String startUtc = "2019-01-07 00:00:00.000";
    @Configurable("Single end UTC exclusive") public String endUtc = "2019-01-14 00:00:00.000";
    @Configurable("Batch year") public int batchYear = 2019;
    @Configurable("Batch output directory") public File outputDirectory = new File("data/ticks/incoming/jforex");
    @Configurable("Validated months to protect (comma-separated)") public String validatedMonths = "";

    private BufferedWriter writer;
    private IConsole console;
    private long start;
    private long end;
    private long sequence;
    private int activeMonth;
    private File activeTemporary;
    private File activeFinal;
    private boolean yearBatch;
    private final Set<Integer> protectedMonths = new HashSet<Integer>();

    public void onStart(IContext context) throws JFException {
        console = context.getConsole();
        yearBatch = "YEAR_BATCH".equalsIgnoreCase(mode.trim());
        if (!yearBatch && !"SINGLE_UNIT".equalsIgnoreCase(mode.trim())) throw new JFException("Unknown mode: " + mode);
        if (yearBatch) initializeYearBatch(); else initializeSingle();
    }

    private void initializeSingle() throws JFException {
        start = parseUtc(startUtc);
        end = parseUtc(endUtc);
        if (start >= end) throw new JFException("start must precede end");
        if (outputFile.exists()) throw new JFException("refusing to overwrite existing export: " + outputFile);
        writer = openNew(outputFile);
    }

    private void initializeYearBatch() throws JFException {
        if (batchYear < 2019 || batchYear > 2023) throw new JFException("batch year must be 2019 through 2023");
        if (!outputDirectory.isDirectory() && !outputDirectory.mkdirs()) throw new JFException("cannot create output directory");
        for (String value : validatedMonths.split(",")) {
            if (!value.trim().isEmpty()) protectedMonths.add(Integer.parseInt(value.trim()));
        }
        Calendar utc = new GregorianCalendar(TimeZone.getTimeZone("UTC"));
        utc.clear(); utc.set(batchYear, Calendar.JANUARY, 1);
        start = utc.getTimeInMillis(); utc.add(Calendar.YEAR, 1); end = utc.getTimeInMillis();
    }

    public void onTick(Instrument tickInstrument, ITick tick) throws JFException {
        if (!instrument.equals(tickInstrument) || tick.getTime() < start || tick.getTime() >= end) return;
        if (yearBatch) routeYearTick(tick); else writeTick(tick);
    }

    private void routeYearTick(ITick tick) throws JFException {
        Calendar utc = new GregorianCalendar(TimeZone.getTimeZone("UTC"));
        utc.setTimeInMillis(tick.getTime());
        int month = utc.get(Calendar.MONTH) + 1;
        if (month != activeMonth) {
            finalizeActive();
            activeMonth = month;
            sequence = 0;
            activeFinal = new File(outputDirectory, monthlyFilename(month));
            activeTemporary = new File(activeFinal.getPath() + ".part");
            if (activeFinal.exists()) {
                if (!protectedMonths.contains(month)) throw new JFException("existing unprotected monthly file: " + activeFinal);
                console.getOut().println("Skipping protected validated month: " + activeFinal);
                writer = null;
                return;
            }
            try { Files.deleteIfExists(activeTemporary.toPath()); }
            catch (IOException error) { throw new JFException("cannot clear incomplete temporary file: " + error.getMessage()); }
            writer = openNew(activeTemporary);
        }
        if (writer != null) writeTick(tick);
    }

    private String monthlyFilename(int month) {
        Calendar utc = new GregorianCalendar(TimeZone.getTimeZone("UTC"));
        utc.clear(); utc.set(batchYear, month - 1, 1);
        SimpleDateFormat name = new SimpleDateFormat("yyyyMMdd'T'HHmmss'Z'");
        name.setTimeZone(TimeZone.getTimeZone("UTC"));
        String from = name.format(utc.getTime()); utc.add(Calendar.MONTH, 1);
        return instrument.name() + "_" + from + "_" + name.format(utc.getTime()) + "_JFOREX_TICKS.csv";
    }

    private BufferedWriter openNew(File path) throws JFException {
        try {
            BufferedWriter output = new BufferedWriter(new OutputStreamWriter(new FileOutputStream(path, false), StandardCharsets.UTF_8));
            output.write("timestamp_utc_ms,pair,bid,ask,bid_volume,ask_volume,source_sequence\n");
            return output;
        } catch (IOException error) { throw new JFException("cannot open export: " + error.getMessage()); }
    }

    private void writeTick(ITick tick) throws JFException {
        try {
            writer.write(String.format(Locale.ROOT, "%d,%s,%.10f,%.10f,%.10f,%.10f,%d%n",
                tick.getTime(), instrument.name(), tick.getBid(), tick.getAsk(),
                tick.getBidVolume(), tick.getAskVolume(), sequence++));
        } catch (IOException error) { throw new JFException("export write failed: " + error.getMessage()); }
    }

    private void finalizeActive() throws JFException {
        if (writer == null) return;
        try {
            writer.flush(); writer.close(); writer = null;
            if (!yearBatch) return;
            try { Files.move(activeTemporary.toPath(), activeFinal.toPath(), StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException error) { Files.move(activeTemporary.toPath(), activeFinal.toPath()); }
        } catch (IOException error) { throw new JFException("monthly finalization failed: " + error.getMessage()); }
    }

    private long parseUtc(String value) throws JFException {
        try {
            SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS");
            format.setLenient(false); format.setTimeZone(TimeZone.getTimeZone("UTC"));
            return format.parse(value).getTime();
        } catch (Exception error) { throw new JFException("invalid UTC parameter: " + value); }
    }

    public void onStop() throws JFException { finalizeActive(); }
    public void onAccount(IAccount account) {}
    public void onMessage(IMessage message) {}
    public void onBar(Instrument instrument, Period period, IBar askBar, IBar bidBar) {}
}
