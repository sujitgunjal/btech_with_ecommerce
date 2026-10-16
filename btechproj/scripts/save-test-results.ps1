param(
    [string]$OutputFile = 'project-test-results.json'
)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Net.Http

$projectRoot = Split-Path -Parent $PSScriptRoot
$outputDirectory = Join-Path $projectRoot 'output'
$outputPath = Join-Path $outputDirectory $OutputFile

New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [ValidateSet('GET', 'POST')]
        [string]$Method = 'GET',

        [object]$Body,

        [hashtable]$Headers
    )

    try {
        $httpClient = New-Object System.Net.Http.HttpClient
        $httpMethod = New-Object System.Net.Http.HttpMethod -ArgumentList $Method
        $request = New-Object System.Net.Http.HttpRequestMessage -ArgumentList $httpMethod, $Uri

        if ($null -ne $Body) {
            $jsonBody = $Body | ConvertTo-Json -Compress
            $request.Content = New-Object System.Net.Http.StringContent -ArgumentList @($jsonBody, [Text.Encoding]::UTF8, 'application/json')
        }

        if ($null -ne $Headers) {
            foreach ($header in $Headers.GetEnumerator()) {
                [void]$request.Headers.TryAddWithoutValidation($header.Key, [string]$header.Value)
            }
        }

        $response = $httpClient.SendAsync($request).GetAwaiter().GetResult()
        $responseContent = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $parsedBody = $null

        if (-not [string]::IsNullOrWhiteSpace($responseContent)) {
            try {
                $parsedBody = $responseContent | ConvertFrom-Json
            }
            catch {
                $parsedBody = $responseContent
            }
        }

        return [ordered]@{
            status_code = [int]$response.StatusCode
            ok = $response.IsSuccessStatusCode
            body = $parsedBody
        }
    }
    catch {
        return [ordered]@{
            status_code = $null
            ok = $false
            error = $_.Exception.Message
        }
    }
}

function Invoke-PrometheusQuery {
    param([Parameter(Mandatory = $true)][string]$Query)

    $encodedQuery = [Uri]::EscapeDataString($Query)
    return Invoke-JsonRequest -Uri "http://localhost:9090/api/v1/query?query=$encodedQuery"
}

function Invoke-LokiRangeQuery {
    param([Parameter(Mandatory = $true)][string]$Query)

    $start = [DateTimeOffset]::UtcNow.AddMinutes(-10).ToUnixTimeMilliseconds() * 1000000
    $end = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() * 1000000
    $encodedQuery = [Uri]::EscapeDataString($Query)
    $uri = "http://localhost:3100/loki/api/v1/query_range?query=$encodedQuery&start=$start&end=$end&limit=10&direction=backward"
    return Invoke-JsonRequest -Uri $uri
}

function Test-Result {
    param(
        [Parameter(Mandatory = $true)][bool]$Passed,
        [Parameter(Mandatory = $true)][object]$Details
    )

    return [ordered]@{
        status = if ($Passed) { 'PASS' } else { 'FAIL' }
        details = $Details
    }
}

$tests = [ordered]@{}

$composeOutput = docker compose ps --format json 2>&1
$composeServices = @()
$composeParseError = $null
try {
    $composeServices = @($composeOutput | ConvertFrom-Json)
}
catch {
    $composeParseError = $_.Exception.Message
}

$expectedServices = @(
    'cadvisor', 'postgres', 'grafana', 'jaeger', 'loki',
    'order-service', 'otel-collector', 'product-service', 'prometheus', 'user-service'
)
$runningServices = @($composeServices | Where-Object { $_.State -eq 'running' } | ForEach-Object { $_.Service })
$missingServices = @($expectedServices | Where-Object { $_ -notin $runningServices })
$tests.services = Test-Result -Passed ($null -eq $composeParseError -and $missingServices.Count -eq 0) -Details ([ordered]@{
    expected = $expectedServices
    running = $runningServices
    missing = $missingServices
    compose_parse_error = $composeParseError
})

$health = [ordered]@{}
foreach ($service in @('user', 'product', 'order')) {
    $port = switch ($service) {
        'user' { 8001 }
        'product' { 8002 }
        'order' { 8003 }
    }
    $health[$service] = Invoke-JsonRequest -Uri "http://localhost:$port/health"
}
$healthPassed = @($health.Values | Where-Object { -not $_.ok }).Count -eq 0
$tests.health = Test-Result -Passed $healthPassed -Details $health

$orderBody = @{ user_id = 1; product_id = 1; quantity = 1 }
$createdOrder = Invoke-JsonRequest -Uri 'http://localhost:8003/orders' -Method POST -Body $orderBody
$orderPassed = $createdOrder.ok -and $createdOrder.body.status -eq 'created'
$tests.order_creation = Test-Result -Passed $orderPassed -Details ([ordered]@{
    request = $orderBody
    response = $createdOrder
})

$requestMetric = Invoke-PrometheusQuery -Query 'app_http_request_count_total'
$errorMetric = Invoke-PrometheusQuery -Query 'app_http_error_count_total'
$durationMetric = Invoke-PrometheusQuery -Query 'app_http_request_duration_seconds_count'
$metricDetails = [ordered]@{
    request_series = @($requestMetric.body.data.result).Count
    error_series = @($errorMetric.body.data.result).Count
    duration_series = @($durationMetric.body.data.result).Count
    request_query_ok = $requestMetric.ok
    error_query_ok = $errorMetric.ok
    duration_query_ok = $durationMetric.ok
}
$tests.prometheus = Test-Result -Passed ($requestMetric.ok -and $errorMetric.ok -and $durationMetric.ok) -Details $metricDetails

$lokiQuery = '{service_name="order-service"} |= "Order created successfully"'
$loki = $null
for ($attempt = 0; $attempt -lt 6; $attempt++) {
    $loki = Invoke-LokiRangeQuery -Query $lokiQuery
    $lokiResultCount = 0
    if ($loki.ok -and $null -ne $loki.body.data) {
        $lokiResultCount = @($loki.body.data.result).Count
    }
    if ($lokiResultCount -gt 0) {
        break
    }
    Start-Sleep -Seconds 2
}
$logStreams = @()
if ($loki.ok -and $null -ne $loki.body.data) {
    $logStreams = @($loki.body.data.result | ForEach-Object {
        $_.values | ForEach-Object {
            [ordered]@{
                timestamp = $_[0]
                message = $_[1]
            }
        }
    })
}
$tests.loki = Test-Result -Passed ($loki.ok -and $logStreams.Count -gt 0) -Details ([ordered]@{
    query = $lokiQuery
    matching_entries = $logStreams.Count
    entries = @($logStreams | Select-Object -First 10)
})

$jaegerServices = Invoke-JsonRequest -Uri 'http://localhost:16686/api/services'
$traceQuery = Invoke-JsonRequest -Uri 'http://localhost:16686/api/traces?service=order-service&operation=POST%20%2Forders&limit=1&lookback=1h'
$trace = $null
if ($traceQuery.ok) {
    $trace = @($traceQuery.body.data)[0]
}
$traceServiceNames = @()
$traceOperations = @()
if ($null -ne $trace) {
    $traceServiceNames = @($trace.processes.PSObject.Properties | ForEach-Object { $_.Value.serviceName } | Sort-Object -Unique)
    $traceOperations = @($trace.spans | ForEach-Object { $_.operationName } | Sort-Object -Unique)
}
$tracePassed = $jaegerServices.ok -and $traceQuery.ok -and $null -ne $trace -and $traceServiceNames.Count -ge 3
$tests.jaeger = Test-Result -Passed $tracePassed -Details ([ordered]@{
    services = @($jaegerServices.body.data)
    trace_id = if ($null -ne $trace) { $trace.traceID } else { $null }
    span_count = if ($null -ne $trace) { @($trace.spans).Count } else { 0 }
    trace_services = $traceServiceNames
    span_operations = $traceOperations
})

$grafanaHealth = Invoke-JsonRequest -Uri 'http://localhost:3000/api/health'
$grafanaHeaders = @{ Authorization = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes('admin:admin')) }
$grafanaDashboards = Invoke-JsonRequest -Headers $grafanaHeaders -Uri 'http://localhost:3000/api/search?type=dash-db'
$dashboard = @($grafanaDashboards.body)[0]
$grafanaPassed = $grafanaHealth.ok -and $grafanaDashboards.ok -and $null -ne $dashboard
$tests.grafana = Test-Result -Passed $grafanaPassed -Details ([ordered]@{
    health = $grafanaHealth.body
    dashboard = $dashboard
})

$failedTests = @($tests.GetEnumerator() | Where-Object { $_.Value.status -eq 'FAIL' } | ForEach-Object { $_.Key })
$results = [ordered]@{
    generated_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    project = 'AI-Powered-Incident-Investigation-System'
    overall_status = if ($failedTests.Count -eq 0) { 'PASS' } else { 'FAIL' }
    failed_tests = $failedTests
    tests = $tests
}

$results | ConvertTo-Json -Depth 30 | Set-Content -Path $outputPath -Encoding utf8
Write-Output "Saved test results to $outputPath"
Write-Output "Overall status: $($results.overall_status)"
