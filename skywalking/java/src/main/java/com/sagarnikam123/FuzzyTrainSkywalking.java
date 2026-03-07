package com.sagarnikam123;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;
import java.util.Random;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Fake log generator with SkyWalking integration (Java version).
 * 
 * Based on fuzzy-train.py, generates fake logs and sends them to SkyWalking 
 * via the Java agent's gRPC log reporter (logback toolkit).
 * 
 * Logs appear in SkyWalking UI under General Service → <service-name> → Log tab.
 * 
 * Requires SkyWalking Java Agent with logback toolkit configured.
 * 
 * Usage:
 *   java -javaagent:/path/to/skywalking-agent.jar -jar fuzzy-train-skywalking.jar
 *   java -jar fuzzy-train-skywalking.jar --lines-per-second 5
 */
public class FuzzyTrainSkywalking {
    
    private static final Logger logger = LoggerFactory.getLogger(FuzzyTrainSkywalking.class);
    private static final Random random = new Random();
    private static final AtomicBoolean running = new AtomicBoolean(true);
    private static final AtomicLong logCount = new AtomicLong(0);
    private static final AtomicLong traceIdCounter = new AtomicLong(1);
    
    private static final String VERSION = "1.0.0";
    private static final double DETAIL_PROBABILITY = 0.3;
    
    // Log levels (matching fuzzy-train.py)
    private static final List<String> LOG_LEVELS = List.of("INFO", "ERROR", "DEBUG", "WARN");
    
    // Sentences (matching fuzzy-train.py)
    private static final List<String> SENTENCES = List.of(
        "Processing request from client.",
        "Database connection established successfully.",
        "Cache hit ratio is below threshold.",
        "User authentication completed.",
        "API request processing time exceeded limits.",
        "Memory usage is within normal parameters.",
        "Disk I/O operations completed.",
        "Network latency detected on primary interface.",
        "Configuration loaded from environment variables.",
        "Background task scheduler initiated.",
        "Garbage collection cycle completed.",
        "Service health check passed.",
        "Rate limiting applied to incoming requests.",
        "Thread pool resources allocated.",
        "Security policy validation completed.",
        "Data synchronization process started.",
        "Backup procedure executed successfully.",
        "Input validation performed on user data.",
        "Rendering engine initialized with default parameters.",
        "Encryption key rotation completed."
    );
    
    // Default configuration constants
    private static final int DEFAULT_MIN_LOG_LENGTH = 90;
    private static final int DEFAULT_MAX_LOG_LENGTH = 100;
    private static final double DEFAULT_LINES_PER_SECOND = 1.0;
    private static final String DEFAULT_TRACE_ID_TYPE = "pid";
    
    private static String processId;
    
    /**
     * Get process identifier based on environment (PID for local, container ID for containers).
     */
    private static String getProcessId() {
        // Check if running in container
        boolean inContainer = Files.exists(Paths.get("/.dockerenv")) ||
                              Files.exists(Paths.get("/proc/1/cgroup")) ||
                              System.getenv("container") != null ||
                              Files.exists(Paths.get("/run/.containerenv"));
        
        if (inContainer) {
            try {
                String hostname = InetAddress.getLocalHost().getHostName();
                // For Kubernetes pods, extract the hash suffix
                if (hostname.contains("-")) {
                    String[] parts = hostname.split("-");
                    if (parts.length >= 2) {
                        String suffix = parts.length > 2 
                            ? parts[parts.length - 2] + "-" + parts[parts.length - 1]
                            : parts[parts.length - 1];
                        return suffix.length() > 12 ? suffix.substring(0, 12) : suffix;
                    }
                }
                return hostname.length() > 12 ? hostname.substring(0, 12) : hostname;
            } catch (Exception e) {
                return "unknown";
            }
        } else {
            return String.valueOf(ProcessHandle.current().pid());
        }
    }
    
    /**
     * Generate a random log message of specified length.
     */
    private static String generateRandomMessage(int length) {
        StringBuilder message = new StringBuilder();
        while (message.length() < length) {
            String sentence = SENTENCES.get(random.nextInt(SENTENCES.size()));
            if (random.nextDouble() < DETAIL_PROBABILITY) {
                String detail = generateRandomString(random.nextInt(21) + 10);
                sentence += " Details: " + detail;
            }
            message.append(sentence).append(" ");
        }
        return message.substring(0, Math.min(message.length(), length));
    }
    
    /**
     * Generate random alphanumeric string.
     */
    private static String generateRandomString(int length) {
        String chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
        StringBuilder sb = new StringBuilder(length);
        for (int i = 0; i < length; i++) {
            sb.append(chars.charAt(random.nextInt(chars.length())));
        }
        return sb.toString();
    }
    
    /**
     * Generate trace ID for log correlation.
     */
    private static String generateTraceId(boolean includeTraceId, String traceIdType) {
        if (!includeTraceId) {
            return null;
        }
        
        long counter = traceIdCounter.getAndIncrement();
        if ("pid".equals(traceIdType)) {
            return String.format("%s-%08d", processId, counter);
        } else {
            return String.format("%08d", counter);
        }
    }
    
    /**
     * Log message at specified level.
     */
    private static void logAtLevel(String level, String message) {
        switch (level) {
            case "INFO" -> logger.info(message);
            case "WARN" -> logger.warn(message);
            case "ERROR" -> logger.error(message);
            case "DEBUG" -> logger.debug(message);
        }
    }
    
    public static void main(String[] args) {
        // Initialize process ID
        processId = getProcessId();
        
        // Parse arguments
        double linesPerSecond = DEFAULT_LINES_PER_SECOND;
        int minLogLength = DEFAULT_MIN_LOG_LENGTH;
        int maxLogLength = DEFAULT_MAX_LOG_LENGTH;
        boolean includeTraceId = true;
        String traceIdType = DEFAULT_TRACE_ID_TYPE;
        
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--lines-per-second", "-l" -> {
                    if (i + 1 < args.length) {
                        linesPerSecond = Double.parseDouble(args[++i]);
                    }
                }
                case "--min-log-length" -> {
                    if (i + 1 < args.length) {
                        minLogLength = Integer.parseInt(args[++i]);
                    }
                }
                case "--max-log-length" -> {
                    if (i + 1 < args.length) {
                        maxLogLength = Integer.parseInt(args[++i]);
                    }
                }
                case "--no-trace-id" -> includeTraceId = false;
                case "--trace-id-type" -> {
                    if (i + 1 < args.length) {
                        traceIdType = args[++i].toLowerCase();
                    }
                }
                case "--help", "-h" -> {
                    printHelp();
                    return;
                }
                case "--version", "-v" -> {
                    System.out.println("fuzzy-train-skywalking-java " + VERSION);
                    return;
                }
            }
        }
        
        // Validate length params (matching fuzzy-train.py logic)
        if (minLogLength != DEFAULT_MIN_LOG_LENGTH && maxLogLength == DEFAULT_MAX_LOG_LENGTH) {
            maxLogLength = minLogLength;
        } else if (minLogLength == DEFAULT_MIN_LOG_LENGTH && maxLogLength != DEFAULT_MAX_LOG_LENGTH) {
            minLogLength = maxLogLength;
        }
        
        if (minLogLength > maxLogLength) {
            logger.error("min-log-length ({}) cannot be greater than max-log-length ({})", minLogLength, maxLogLength);
            System.exit(1);
        }
        
        // Register shutdown hook
        final long[] finalCount = {0};
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            running.set(false);
            logger.info("Shutdown initiated. Generated {} total log entries.", logCount.get());
        }));
        
        long intervalMs = (long) (1000.0 / linesPerSecond);
        
        String serviceName = System.getenv().getOrDefault("SW_AGENT_NAME", "skywalking-test::fuzzy-train-java");
        String backend = System.getenv().getOrDefault("SW_AGENT_COLLECTOR_BACKEND_SERVICES", "skywalking-satellite.skywalking.svc:11800");
        
        logger.info("Starting fuzzy-train-skywalking-java v{}", VERSION);
        logger.info("Service: {}", serviceName);
        logger.info("Backend: {}", backend);
        logger.info("Rate: {} logs/second", linesPerSecond);
        logger.info("Message length: {}-{} chars", minLogLength, maxLogLength);
        logger.info("Trace ID: {}", includeTraceId ? "enabled (" + traceIdType + ")" : "disabled");
        
        final int finalMinLen = minLogLength;
        final int finalMaxLen = maxLogLength;
        final boolean finalIncludeTraceId = includeTraceId;
        final String finalTraceIdType = traceIdType;
        
        while (running.get()) {
            try {
                String level = LOG_LEVELS.get(random.nextInt(LOG_LEVELS.size()));
                String traceId = generateTraceId(finalIncludeTraceId, finalTraceIdType);
                int messageLength = random.nextInt(finalMaxLen - finalMinLen + 1) + finalMinLen;
                String message = generateRandomMessage(messageLength);
                
                // Add trace_id to message if enabled (for visibility in logs)
                String fullMessage = traceId != null ? "[" + traceId + "] " + message : message;
                
                logAtLevel(level, fullMessage);
                
                long count = logCount.incrementAndGet();
                if (count % 100 == 0) {
                    logger.info("Generated {} log entries", count);
                }
                
                Thread.sleep(intervalMs);
                
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            } catch (Exception e) {
                logger.error("Error generating log: {}", e.getMessage());
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }
        
        logger.info("Shutdown complete. Generated {} total log entries.", logCount.get());
    }
    
    private static void printHelp() {
        System.out.println("""
            fuzzy-train-skywalking-java - Fake log generator with SkyWalking integration
            
            Based on fuzzy-train.py, generates fake logs and sends them to SkyWalking
            via the Java agent's gRPC log reporter (logback toolkit).
            
            Usage:
              java -javaagent:/sky/agent/skywalking-agent.jar -jar fuzzy-train-skywalking.jar [options]
            
            Basic Options:
              -l, --lines-per-second <n>  Generation rate (default: 1)
              -h, --help                  Show this help message
              -v, --version               Show version
            
            Log Content:
              --min-log-length <n>        Minimum message length in characters (default: 90)
              --max-log-length <n>        Maximum message length in characters (default: 100)
            
            Field Control:
              --no-trace-id               Exclude trace_id field
              --trace-id-type <type>      Trace ID type: pid or integer (default: pid)
            
            Environment Variables:
              SW_AGENT_NAME                         Service name in SkyWalking
              SW_AGENT_COLLECTOR_BACKEND_SERVICES   Satellite/OAP endpoint
              SW_GRPC_LOG_SERVER_HOST               Log server host
              SW_GRPC_LOG_SERVER_PORT               Log server port
            
            Examples:
              # Default: 1 log per second
              java -javaagent:/sky/agent/skywalking-agent.jar -jar fuzzy-train-skywalking.jar
              
              # High volume: 10 logs per second
              java -javaagent:/sky/agent/skywalking-agent.jar -jar fuzzy-train-skywalking.jar -l 10
              
              # Custom message length
              java -javaagent:/sky/agent/skywalking-agent.jar -jar fuzzy-train-skywalking.jar \\
                --min-log-length 150 --max-log-length 200
            """);
    }
}
