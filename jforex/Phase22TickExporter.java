package jforex;

import com.dukascopy.api.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.text.SimpleDateFormat;
import java.util.*;

@RequiresFullAccess
public class Phase22TickExporter implements IStrategy {
    public enum ExportMode { SINGLE_UNIT, YEAR_BATCH }

    @Configurable("Mode") public ExportMode mode = ExportMode.YEAR_BATCH;
    @Configurable("Instrument") public Instrument instrument = Instrument.EURUSD;
    @Configurable("Single output CSV") public File outputFile = new File("EURUSD_20190107T000000Z_20190114T000000Z_JFOREX_TICKS.csv");
    @Configurable("Single start UTC inclusive") public String startUtc = "2019-01-07 00:00:00.000";
    @Configurable("Single end UTC exclusive") public String endUtc = "2019-01-14 00:00:00.000";
    @Configurable("Batch year") public int batchYear = 2019;
    @Configurable("Batch output directory") public File outputDirectory = new File("C:\\Users\\derek\\Desktop\\Vcodeee\\data\\ticks\\incoming\\jforex");
    @Configurable("Validated months to protect (comma-separated)") public String validatedMonths = "";

    private BufferedWriter writer;
    private IConsole console;
    private long start, end, sequence, activeMonthTicks, totalTicks;
    private int activeMonth, monthsWritten;
    private File activeTemporary, activeFinal;
    private boolean yearBatch, failed;
    private final Set<Integer> protectedMonths = new HashSet<Integer>();

    public void onStart(IContext context) throws JFException {
        console = context.getConsole();
        if (mode == null) throw new JFException("Mode is required");
        yearBatch = mode == ExportMode.YEAR_BATCH;
        log("PHASE22_EXPORT_MODE=" + mode.name());
        log("INSTRUMENT=" + instrument);
        if (yearBatch) initializeYearBatch(); else initializeSingle();
    }

    private void initializeSingle() throws JFException {
        start = parseUtc(startUtc); end = parseUtc(endUtc);
        log("TESTER_EXPECTED_START=" + formatUtc(start));
        log("TESTER_EXPECTED_END=" + formatUtc(end));
        if (start >= end) throw new JFException("start must precede end");
        if (outputFile.exists()) throw new JFException("refusing to overwrite existing export: " + outputFile);
        writer = openNew(outputFile);
    }

    private void initializeYearBatch() throws JFException {
        if (batchYear < 2019 || batchYear > 2023) throw new JFException("batch year must be 2019 through 2023");
        parseProtectedMonths();
        if (!outputDirectory.isAbsolute()) throw new JFException("Batch output directory must be an absolute Windows path: " + outputDirectory);
        try { outputDirectory = outputDirectory.getCanonicalFile(); }
        catch (IOException error) { throw new JFException("cannot canonicalize Batch output directory: " + error.getMessage()); }
        if (!outputDirectory.isDirectory()) throw new JFException("Batch output directory does not exist: " + outputDirectory);
        if (!Files.isWritable(outputDirectory.toPath())) throw new JFException("Batch output directory is not writable: " + outputDirectory);
        Calendar utc = new GregorianCalendar(TimeZone.getTimeZone("UTC"));
        utc.clear(); utc.set(batchYear, Calendar.JANUARY, 1);
        start = utc.getTimeInMillis(); utc.add(Calendar.YEAR, 1); end = utc.getTimeInMillis();
        log("BATCH_YEAR=" + batchYear);
        log("BATCH_OUTPUT_DIRECTORY=" + outputDirectory.getAbsolutePath());
        log("PROTECTED_MONTHS=" + protectedMonthText());
        log("TESTER_EXPECTED_START=" + formatUtc(start));
        log("TESTER_EXPECTED_END=" + formatUtc(end));
        for (int month = 1; month <= 12; month++) {
            File expected = monthlyFile(month);
            if (protectedMonths.contains(month)) {
                if (!expected.isFile()) throw new JFException("protected monthly file does not exist: " + expected);
                log(String.format(Locale.ROOT, "MONTH_%02d=PROTECTED -> %s", month, expected.getAbsolutePath()));
            } else {
                if (expected.exists()) throw new JFException("existing unprotected monthly file: " + expected);
                log(String.format(Locale.ROOT, "MONTH_%02d=PENDING -> %s", month, expected.getAbsolutePath()));
            }
        }
        log("YEAR_BATCH_STARTED");
    }

    private void parseProtectedMonths() throws JFException {
        for (String value : validatedMonths.split(",")) {
            String trimmed = value.trim();
            if (trimmed.isEmpty()) continue;
            try {
                int month = Integer.parseInt(trimmed);
                if (month < 1 || month > 12) throw new NumberFormatException();
                protectedMonths.add(month);
            } catch (NumberFormatException error) {
                throw new JFException("protected months must contain only integers 1 through 12: " + validatedMonths);
            }
        }
    }

    public void onTick(Instrument tickInstrument, ITick tick) throws JFException {
        if (!instrument.equals(tickInstrument)) return;
        try {
            if (yearBatch) routeYearTick(tick);
            else if (tick.getTime() >= start && tick.getTime() < end) writeTick(tick);
        } catch (JFException error) { failed = true; throw error; }
    }

    private void routeYearTick(ITick tick) throws JFException {
        Calendar utc = new GregorianCalendar(TimeZone.getTimeZone("UTC"));
        utc.setTimeInMillis(tick.getTime());
        if (utc.get(Calendar.YEAR) != batchYear || tick.getTime() < start || tick.getTime() >= end) return;
        totalTicks++;
        int month = utc.get(Calendar.MONTH) + 1;
        if (month != activeMonth) initializeMonth(month);
        if (writer != null) { writeTick(tick); activeMonthTicks++; }
    }

    private void initializeMonth(int month) throws JFException {
        finalizeActive();
        activeMonth = month; sequence = 0; activeMonthTicks = 0;
        activeFinal = monthlyFile(month);
        activeTemporary = new File(activeFinal.getPath() + ".part");
        if (protectedMonths.contains(month)) {
            writer = null;
            log("MONTH_PROTECTED " + month + " " + activeFinal.getAbsolutePath());
            return;
        }
        if (activeFinal.exists()) throw new JFException("existing unprotected monthly file: " + activeFinal);
        try { Files.deleteIfExists(activeTemporary.toPath()); }
        catch (IOException error) { throw new JFException("cannot clear incomplete temporary file: " + error.getMessage()); }
        writer = openNew(activeTemporary);
        log("MONTH_WRITER_OPENED " + month + " " + activeTemporary.getAbsolutePath());
    }

    private File monthlyFile(int month) { return new File(outputDirectory, monthlyFilename(month)); }

    private String monthlyFilename(int month) {
        Calendar utc = new GregorianCalendar(TimeZone.getTimeZone("UTC"));
        utc.clear(); utc.set(batchYear, month - 1, 1);
        SimpleDateFormat name = new SimpleDateFormat("yyyyMMdd''T''HHmmss''Z''");
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
            monthsWritten++;
            log("MONTH_FINALIZED " + activeMonth + " " + activeMonthTicks + " " + activeFinal.getAbsolutePath());
        } catch (IOException error) { throw new JFException("monthly finalization failed: " + error.getMessage()); }
    }

    public void onStop() throws JFException {
        if (failed) { closeFailedWriter(); return; }
        finalizeActive();
        if (yearBatch) {
            int pending = 12 - protectedMonths.size();
            if (pending > 0 && monthsWritten == 0) {
                log("YEAR_BATCH_NO_OUTPUT_ERROR");
                throw new JFException("YEAR_BATCH produced no pending monthly output");
            }
            if (monthsWritten != pending) throw new JFException("YEAR_BATCH incomplete: finalized " + monthsWritten + " of " + pending + " pending months");
            log("YEAR_BATCH_COMPLETED " + monthsWritten + " " + protectedMonths.size() + " " + totalTicks);
        }
    }

    private void closeFailedWriter() throws JFException {
        if (writer == null) return;
        try { writer.close(); writer = null; }
        catch (IOException error) { throw new JFException("cannot close failed partial output: " + error.getMessage()); }
    }

    private long parseUtc(String value) throws JFException {
        try {
            SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS");
            format.setLenient(false); format.setTimeZone(TimeZone.getTimeZone("UTC"));
            return format.parse(value).getTime();
        } catch (Exception error) { throw new JFException("invalid UTC parameter: " + value); }
    }

    private String formatUtc(long value) {
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS ''UTC''");
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        return format.format(new Date(value));
    }

    private String protectedMonthText() {
        List<Integer> values = new ArrayList<Integer>(protectedMonths);
        Collections.sort(values);
        return values.toString();
    }

    private void log(String message) { console.getOut().println(message); }
    public void onAccount(IAccount account) {}
    public void onMessage(IMessage message) {}
    public void onBar(Instrument instrument, Period period, IBar askBar, IBar bidBar) {}
}