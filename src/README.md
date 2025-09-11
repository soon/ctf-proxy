# CTF Proxy Post-Processor

A lightweight log processor and dashboard for CTF competitions that monitors HTTP traffic through the Envoy proxy and provides real-time analytics.

## Features

- **Real-time log processing**: Continuously monitors Envoy access logs
- **Efficient SQLite storage**: Normalized data schema for fast queries
- **Path normalization**: Automatically groups similar paths (e.g., `/user/123` → `/user/{id}`)
- **Comprehensive statistics**: Request counts, response times, error rates, etc.
- **Attack detection**: Identifies suspicious activities and common attack patterns
- **CLI dashboard**: Multiple views for different analysis needs
- **Export functionality**: JSON export for integration with other tools

## Architecture

### Components

1. **post_processor.py** - Background daemon that reads Envoy logs and populates SQLite DB
2. **dashboard.py** - CLI tool for viewing statistics and analysis
3. **Database schema** - Optimized for CTF scenarios with the following tables:
   - `requests` - Individual HTTP requests with normalized paths
   - `path_stats` - Aggregated statistics per path
   - `method_stats` - HTTP method distribution
   - `status_stats` - Response code distribution
   - `hourly_stats` - Time-based traffic patterns
   - `query_param_stats` - Query parameter analysis

### Data Collection

The post-processor extracts and analyzes:
- Request timestamps and durations
- HTTP methods and response codes
- Normalized URL paths (with ID/UUID/hash abstraction)
- Query parameters and their usage patterns
- Traffic volume and error rates
- Suspicious activity patterns

## Installation

1. Ensure Envoy is configured with JSON access logging:
```yaml
access_log:
- name: envoy.access_loggers.file
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog
    path: /var/log/envoy/http_access.log
    json_format:
      start_time: "%START_TIME%"
      method: "%REQ(:METHOD)%"
      path: "%REQ(X-ENVOY-ORIGINAL-PATH?:PATH)%"
      status: "%RESPONSE_CODE%"
      duration_ms: "%DURATION%"
      # ... other fields
```

2. Start the post-processor:
```bash
# Development
make post-processor

# Background with custom paths
python3 post_processor.py /var/log/envoy/http_access.log ./proxy_stats.db

# Using the startup script
./start_post_processor.sh
```

3. View statistics:
```bash
# Full dashboard
make dashboard

# Live monitoring
make dashboard-live

# Specific views
python3 dashboard.py --overview
python3 dashboard.py --paths 20
python3 dashboard.py --attacks 10
```

## Usage Examples

### Basic Monitoring
```bash
# Start post-processor in background
python3 post_processor.py &

# View live statistics
python3 dashboard.py --all
```

### CTF Competition Analysis
```bash
# Monitor suspicious activities
python3 dashboard.py --attacks 20

# Check most targeted endpoints
python3 dashboard.py --paths 50

# Analyze query parameters for flag extraction attempts
python3 dashboard.py --params 30

# Search for specific attack patterns
python3 dashboard.py --search "admin"
python3 dashboard.py --search "flag"
python3 dashboard.py --search "../"
```

### Export for Further Analysis
```bash
python3 dashboard.py --export ctf_stats.json
```

## Dashboard Views

### Overview
- Total request count
- Unique path count  
- Recent activity (last hour)

### Top Paths
- Most frequently accessed endpoints
- Response time statistics
- Status code distribution per path
- Traffic volume

### HTTP Methods
- Method distribution (GET, POST, etc.)
- Usage percentages

### Status Codes  
- Response code breakdown
- Error rate analysis
- Success vs failure ratios

### Hourly Traffic
- Time-based request patterns
- Performance trends
- Error rate over time

### Query Parameters
- Most common parameters
- Unique value counts
- Parameter usage frequency

### Suspicious Activity
- 4xx/5xx responses
- Directory traversal attempts
- Admin panel access attempts  
- Flag-related requests

## CTF-Specific Features

### Path Normalization
Automatically groups similar paths for better analysis:
- `/user/123` → `/user/{id}`
- `/api/flag/uuid-here` → `/api/flag/{uuid}`
- `/files/hash123...` → `/files/{hash}`

### Attack Pattern Detection
Identifies common CTF attack vectors:
- Directory traversal (`../`, `..%2f`)
- Admin panel probing (`/admin`, `/wp-admin`)
- Flag extraction attempts (`flag`, `FLAG`, `ctf`)
- Script injection patterns
- Unusual HTTP methods

### Performance Monitoring
Critical for CTF where services must stay online:
- Response time tracking per endpoint
- Error rate monitoring
- Traffic spike detection
- Service health indicators

## Deployment

### Systemd Service
```bash
# Copy service file
sudo cp ctf-post-processor.service /etc/systemd/system/

# Enable and start
sudo systemctl enable ctf-post-processor
sudo systemctl start ctf-post-processor

# Check status
sudo systemctl status ctf-post-processor
```

### Docker Integration
The post-processor works with the existing docker-compose setup:
```bash
make install    # Start Envoy proxy
make post-processor  # Start log processing
```

## Performance

- **Memory usage**: ~10-50MB for typical CTF workloads
- **CPU usage**: Minimal when no new logs
- **Disk usage**: ~1MB per 10k requests (depending on path diversity)
- **Processing speed**: ~1000 requests/second on modern hardware

## Troubleshooting

### Log File Issues
- Ensure Envoy has write permissions to log directory
- Check log file rotation doesn't break tailing
- Verify JSON format matches expected schema

### Database Issues  
- SQLite file permissions for read/write access
- Database corruption recovery: delete `.db` file to recreate
- Position file tracks last processed log line

### Memory Issues
- Large log files: processor tracks position to avoid re-processing
- Database growth: implement log rotation and archival
- Long-running deployment: monitor memory usage

## Security Considerations

- Database contains request data - secure appropriately
- Log files may contain sensitive information
- Dashboard output could reveal service internals
- Consider access controls in multi-team environments
