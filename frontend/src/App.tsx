import React, { useEffect, useState } from "react";
import axios from "axios";

interface Device {
  id: number;
  ip_address: string;
  mac_address: string;
  hostname?: string;
  vendor?: string;
  status: string;
}

interface Metric {
  id: number;
  timestamp: string;
  download_speed?: number;
  upload_speed?: number;
  latency?: number;
  packet_loss?: number;
}

interface Overview {
  device_count: number;
  active_alerts: number;
  latest_metric: Metric | null;
}

function App() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [showAllDevices, setShowAllDevices] = useState(false);
  const [latestMetric, setLatestMetric] = useState<Metric | null>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [runningTest, setRunningTest] = useState(false);
  const [downloadMbps, setDownloadMbps] = useState<number | null>(null);
  const [uploadMbps, setUploadMbps] = useState<number | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [devicesRes, metricRes, alertRes, overviewRes] = await Promise.all([
          axios.get(`http://localhost:8000/api/devices${showAllDevices ? '?all=true' : ''}`),
          axios.get("http://localhost:8000/api/metrics/latest"),
          axios.get("http://localhost:8000/api/alerts"),
          axios.get("http://localhost:8000/api/overview"),
        ]);
        setDevices(devicesRes.data);
        setLatestMetric(metricRes.data);
        setAlerts(alertRes.data);
        setOverview(overviewRes.data);
      } catch (error) {
        console.error("Fetch error", error);
      }
    };

    fetchData();
  }, []);

  // refetch devices when showAllDevices toggles
  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const res = await axios.get(`http://localhost:8000/api/devices${showAllDevices ? '?all=true' : ''}`);
        setDevices(res.data);
      } catch (err) {
        console.error('devices fetch failed', err);
      }
    };
    fetchDevices();
  }, [showAllDevices]);

  // WebSocket for live metric updates
  useEffect(() => {
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket("ws://localhost:8000/ws/metrics");
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data?.type === "metric") {
            const payload = data.payload;
            setLatestMetric(payload);
            setOverview((prev) => {
              if (!prev) return prev;
              return { ...prev, latest_metric: payload } as Overview;
            });
          } else if (data?.type === "alert") {
            const payload = data.payload;
            setAlerts((prev) => [payload, ...prev].slice(0, 20));
          } else {
            // backward-compat: plain metric object
            setLatestMetric(data);
          }
        } catch (err) {
          console.error("WS parse error", err);
        }
      };
      ws.onopen = () => console.debug("WS connected to /ws/metrics");
      ws.onclose = () => console.debug("WS disconnected");
      ws.onerror = (e) => console.error("WS error", e);
    } catch (err) {
      console.error("WebSocket init error", err);
    }

    return () => {
      try {
        if (ws) ws.close();
      } catch (e) {
        /* ignore */
      }
    };
  }, []);

  // Polling fallback: fetch latest metric and alerts periodically
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const [metricRes, alertRes, overviewRes] = await Promise.all([
          axios.get("http://localhost:8000/api/metrics/latest"),
          axios.get("http://localhost:8000/api/alerts"),
          axios.get("http://localhost:8000/api/overview"),
        ]);
        setLatestMetric(metricRes.data);
        setAlerts(alertRes.data || []);
        setOverview(overviewRes.data);
      } catch (err) {
        // ignore polling errors
      }
    }, 15000);

    return () => clearInterval(interval);
  }, []);

  const runSpeedTest = async (mb = 10) => {
    setRunningTest(true);
    setDownloadMbps(null);
    setUploadMbps(null);
    try {
      // download test
      const dlStart = performance.now();
      const dlResp = await fetch(`http://localhost:8000/api/debug/speedtest/download?mb=${mb}`);
      const reader = dlResp.body?.getReader();
      let received = 0;
      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          received += (value?.length || 0);
        }
      }
      const dlTime = (performance.now() - dlStart) / 1000;
      const dlMbps = (received * 8) / (1000 * 1000) / dlTime;
      setDownloadMbps(Number(dlMbps.toFixed(2)));

      // upload test
      const size = mb * 1024 * 1024;
      const buf = new Uint8Array(size);
      for (let i = 0; i < buf.length; i += 16384) buf[i] = 0;
      const blob = new Blob([buf]);
      const ulStart = performance.now();
      const ulResp = await fetch(`http://localhost:8000/api/debug/speedtest/upload`, { method: 'POST', body: blob });
      const ulJson = await ulResp.json();
      const ulTime = (performance.now() - ulStart) / 1000;
      const ulBytes = ulJson?.bytes || size;
      const ulMbps = (ulBytes * 8) / (1000 * 1000) / ulTime;
      setUploadMbps(Number(ulMbps.toFixed(2)));
    } catch (err) {
      console.error('speedtest failed', err);
    } finally {
      setRunningTest(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <header className="mb-8">
        <h1 className="text-4xl font-semibold">NetPulse Campus</h1>
        <p className="mt-2 text-slate-400">Smart network monitoring for hostels, colleges, and small organizations.</p>
      </header>

      <section className="grid gap-4 md:grid-cols-3 mb-8">
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
          <button className="rounded-md bg-sky-600 px-4 py-2 font-semibold" onClick={() => runSpeedTest(10)} disabled={runningTest}>
            {runningTest ? 'Running...' : 'Run Speed Test (10 MB)'}
          </button>
          <div className="mt-3 text-sm text-slate-400">
            {downloadMbps !== null && <div>Download: {downloadMbps} Mbps</div>}
            {uploadMbps !== null && <div>Upload: {uploadMbps} Mbps</div>}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Download</p>
          <p className="mt-4 text-3xl font-semibold">{latestMetric?.download_speed ?? "--"} Mbps</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Upload</p>
          <p className="mt-4 text-3xl font-semibold">{latestMetric?.upload_speed ?? "--"} Mbps</p>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-4 mb-8">
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Devices</p>
          <p className="mt-4 text-3xl font-semibold">{overview?.device_count ?? "--"}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Active Alerts</p>
          <p className="mt-4 text-3xl font-semibold">{overview?.active_alerts ?? "--"}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Last Updated</p>
          <p className="mt-4 text-3xl font-semibold">{overview?.latest_metric?.timestamp ? new Date(overview.latest_metric.timestamp).toLocaleTimeString() : "--"}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Packet Loss</p>
          <p className="mt-4 text-3xl font-semibold">{overview?.latest_metric?.packet_loss ?? "--"}%</p>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold mb-4">Active Devices</h2>
            <label className="text-sm text-slate-400">
              <input type="checkbox" className="mr-2" checked={showAllDevices} onChange={(e) => setShowAllDevices(e.target.checked)} />
              Show all devices
            </label>
          </div>
            {devices.length === 0 ? (
              <p className="text-slate-500">No devices found yet.</p>
            ) : (
              devices.map((device) => (
                <div key={device.id} className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="font-semibold">{device.hostname || device.ip_address}</p>
                      <p className="text-sm text-slate-500">{device.vendor || device.mac_address}</p>
                    </div>
                    <span className="rounded-full bg-emerald-500 px-3 py-1 text-xs font-semibold uppercase text-slate-950">{device.status}</span>
                  </div>
                </div>
              ))
            )}
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-lg">
          <h2 className="text-xl font-semibold mb-4">Recent Alerts</h2>
          <div className="space-y-3">
            {alerts.length === 0 ? (
              <p className="text-slate-500">No alerts at the moment.</p>
            ) : (
              alerts.map((alert) => (
                <div key={alert.id} className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                  <p className="font-semibold">{alert.severity.toUpperCase()}</p>
                  <p className="text-sm text-slate-400">{alert.message}</p>
                </div>
              ))
            )}
          </div>
          <p className="mt-4 text-3xl font-semibold">{devices.length ?? "--"}</p>
        </div>
      </section>
    </div>
  );
}

export default App;
