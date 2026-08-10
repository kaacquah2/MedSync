/**
 * SystemHealthPage — live system-wide health dashboard for super admin.
 * All metrics sourced from real API endpoints:
 *   /healthz/               — DB connectivity
 *   /api/csrf/              — API round-trip latency
 *   /api/audit/validate-chain/ — audit chain integrity
 *   /api/audit/             — event counts (filtered by action + date)
 */

import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconActivity,
  IconCheck,
  IconDatabase,
  IconKey,
  IconRefresh,
  IconServer,
  IconShieldCheck,
  IconShieldLock,
  IconWifi,
  IconX,
} from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState, useEffect } from "react";
import { fetchAuditLog, validateAuditChain, fetchCsrf, fetchHealthz } from "@/api/endpoints";

function HealthMetric({
  icon,
  label,
  value,
  status,
  sub,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  status: "ok" | "warn" | "error" | "loading";
  sub?: string;
  color?: string;
}) {
  const statusColor = status === "ok" ? "green" : status === "warn" ? "orange" : status === "error" ? "red" : "gray";
  const StatusIcon  = status === "ok" ? IconCheck : status === "error" ? IconX : IconActivity;

  return (
    <Card withBorder radius="md" p="lg" style={{ borderLeftWidth: 3, borderLeftColor: `var(--mantine-color-${color ?? statusColor}-5)` }}>
      <Group justify="space-between" mb="xs">
        <ThemeIcon size={40} radius="md" color={color ?? statusColor} variant="light">
          {icon}
        </ThemeIcon>
        <Badge color={statusColor} variant="light" size="sm" leftSection={status !== "loading" ? <StatusIcon size={10} /> : undefined}>
          {status === "loading" ? "Checking…" : status.toUpperCase()}
        </Badge>
      </Group>
      <Text size="xl" fw={800}>{value}</Text>
      <Text size="xs" tt="uppercase" fw={700} c="dimmed">{label}</Text>
      {sub && <Text size="xs" c="dimmed" mt={2}>{sub}</Text>}
    </Card>
  );
}

function useAuditCount(action: string, dateFrom: string) {
  return useQuery({
    queryKey: ["health-audit-count", action, dateFrom],
    queryFn: () =>
      fetchAuditLog({ action, date_from: dateFrom, page_size: "1" }).then((r) => r.data.count ?? 0),
    refetchInterval: 30_000,
    staleTime: 20_000,
  });
}

export function SystemHealthPage() {
  const qc = useQueryClient();
  const [apiPingMs, setApiPingMs] = useState<number | null>(null);
  const [apiOk,    setApiOk]     = useState<boolean | null>(null);
  const [now,      setNow]       = useState(dayjs());

  const today = dayjs().format("YYYY-MM-DD");

  // Clock tick for header timestamp
  useEffect(() => {
    const t = setInterval(() => setNow(dayjs()), 10_000);
    return () => clearInterval(t);
  }, []);

  // API ping — measures real round-trip to backend
  useQuery({
    queryKey: ["system-ping"],
    queryFn: async () => {
      const start = performance.now();
      await fetchCsrf();
      const ms = Math.round(performance.now() - start);
      setApiPingMs(ms);
      setApiOk(true);
      return ms;
    },
    refetchInterval: 30_000,
    retry: false,
  });

  // DB health — /healthz/ checks real database connectivity
  const { data: healthzData, isLoading: loadingHealthz } = useQuery({
    queryKey: ["system-healthz"],
    queryFn: fetchHealthz,
    refetchInterval: 30_000,
    retry: false,
  });

  // Audit log total count (all time)
  const { data: auditData, isLoading: loadingAudit, refetch } = useQuery({
    queryKey: ["system-audit-total"],
    queryFn: () => fetchAuditLog({ page_size: "1" }).then((r) => r.data),
    refetchInterval: 30_000,
  });

  // Audit chain integrity
  const { data: chainData, isLoading: loadingChain } = useQuery({
    queryKey: ["system", "chain"],
    queryFn: () => validateAuditChain().then((r) => r.data),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  // Live security event counts for last 24 hours
  const { data: failedLogins }   = useAuditCount("ACCESS_DENIED",    today);
  const { data: breakGlassCount }= useAuditCount("BREAK_GLASS",      today);
  const { data: mfaCount }       = useAuditCount("MFA_VERIFIED",     today);
  const { data: pwdChangeCount } = useAuditCount("PASSWORD_CHANGE",  today);

  // Today's logins
  const { data: loginsTodayData } = useQuery({
    queryKey: ["system", "logins-today", today],
    queryFn: () => fetchAuditLog({ action: "LOGIN", date_from: today, page_size: "1" }).then((r) => r.data.count ?? 0),
    refetchInterval: 30_000,
  });

  const pingStatus: "ok" | "warn" | "error" | "loading" =
    apiPingMs === null ? "loading" : apiOk ? (apiPingMs < 500 ? "ok" : "warn") : "error";

  const dbStatus: "ok" | "warn" | "error" | "loading" =
    loadingHealthz ? "loading" : healthzData?.database === "connected" ? "ok" : "error";

  const encStatus: "ok" | "warn" | "error" | "loading" =
    loadingHealthz ? "loading" : healthzData?.encryption === "ok" ? "ok" : "error";

  const chainStatus: "ok" | "warn" | "error" | "loading" =
    loadingChain ? "loading" : chainData?.chain_valid ? "ok" : "error";

  function refreshAll() {
    void qc.invalidateQueries();
    void refetch();
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconServer size={20} />
          </ThemeIcon>
          <Box>
            <Title order={2}>System Health</Title>
            <Text size="xs" c="dimmed">Last refreshed {now.format("HH:mm:ss")} · Auto-refreshes every 30s</Text>
          </Box>
        </Group>
        <Button leftSection={<IconRefresh size={16} />} variant="subtle" size="sm" onClick={refreshAll}>
          Refresh
        </Button>
      </Group>

      {/* Primary health metrics */}
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 3 }} spacing="md">
        <HealthMetric
          icon={<IconWifi size={20} />}
          label="API Response Time"
          value={apiPingMs === null ? "—" : `${apiPingMs} ms`}
          status={pingStatus}
          sub="GET /api/csrf/ round-trip"
          color="blue"
        />
        <HealthMetric
          icon={<IconDatabase size={20} />}
          label="Database"
          value={loadingHealthz ? "—" : healthzData?.status === "ok" ? "Connected" : "Error"}
          status={dbStatus}
          sub={healthzData?.database ?? "Checking…"}
          color="green"
        />
        <HealthMetric
          icon={<IconShieldCheck size={20} />}
          label="Audit Chain Integrity"
          value={loadingChain ? "Checking…" : chainData?.chain_valid ? "Valid" : "BROKEN"}
          status={chainStatus}
          sub={chainData ? `${chainData.total_entries} entries verified` : undefined}
          color="orange"
        />
        <HealthMetric
          icon={<IconKey size={20} />}
          label="Encryption"
          value={loadingHealthz ? "—" : healthzData?.encryption === "ok" ? "Active" : "Error"}
          status={encStatus}
          sub={
            encStatus === "error" && healthzData?.encryption
              ? healthzData.encryption
              : "Fernet AES field-level encryption"
          }
          color="violet"
        />
        <HealthMetric
          icon={<IconActivity size={20} />}
          label="Total Audit Events"
          value={loadingAudit ? "—" : String(auditData?.count ?? 0)}
          status="ok"
          sub="Cumulative immutable audit log entries"
          color="cyan"
        />
        <HealthMetric
          icon={<IconServer size={20} />}
          label="Logins Today"
          value={loginsTodayData === undefined ? "—" : String(loginsTodayData)}
          status="ok"
          sub={`${today} (UTC)`}
          color="teal"
        />
      </SimpleGrid>

      {/* Live activity + security events */}
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
        {/* DB connectivity detail */}
        <Card withBorder radius="md" p="lg">
          <Group gap="xs" mb="md">
            <ThemeIcon size={32} color="green" variant="light" radius="md">
              <IconDatabase size={18} />
            </ThemeIcon>
            <Text fw={600}>Database Connectivity</Text>
            {!loadingHealthz && (
              <Badge
                color={healthzData?.status === "ok" ? "green" : "red"}
                variant="light"
                size="sm"
                ml="auto"
              >
                {healthzData?.status === "ok" ? "Connected" : "Error"}
              </Badge>
            )}
          </Group>
          {loadingHealthz ? (
            <Skeleton height={60} />
          ) : (
            <Stack gap="xs">
              <Group justify="space-between">
                <Text size="sm">Status</Text>
                <Badge
                  color={healthzData?.status === "ok" ? "green" : "red"}
                  variant="light"
                  size="sm"
                >
                  {healthzData?.status?.toUpperCase() ?? "—"}
                </Badge>
              </Group>
              <Group justify="space-between">
                <Text size="sm">Connection</Text>
                <Text size="sm" fw={500} c={healthzData?.database === "connected" ? "green" : "red"}>
                  {healthzData?.database ?? "—"}
                </Text>
              </Group>
              <Group justify="space-between">
                <Text size="sm">Engine</Text>
                <Text size="sm" fw={500}>Neon Serverless Postgres</Text>
              </Group>
            </Stack>
          )}
        </Card>

        {/* Security events today */}
        <Card withBorder radius="md" p="lg">
          <Group gap="xs" mb="md">
            <ThemeIcon size={32} color="red" variant="light" radius="md">
              <IconShieldLock size={18} />
            </ThemeIcon>
            <Text fw={600}>Security Events Today</Text>
            <Text size="xs" c="dimmed" ml="auto">{today}</Text>
          </Group>
          {loadingAudit ? (
            <Skeleton height={80} />
          ) : (
            <Stack gap="xs">
              {[
                { label: "Failed / denied access", value: failedLogins,   color: "orange" },
                { label: "Break-glass overrides",  value: breakGlassCount,color: "red"    },
                { label: "MFA verifications",      value: mfaCount,       color: "blue"   },
                { label: "Password changes",       value: pwdChangeCount, color: "gray"   },
              ].map((row) => (
                <Group key={row.label} justify="space-between">
                  <Text size="sm">{row.label}</Text>
                  <Badge color={row.color} variant="light" size="sm">
                    {row.value === undefined ? "—" : row.value}
                  </Badge>
                </Group>
              ))}
            </Stack>
          )}
        </Card>
      </SimpleGrid>

      {/* Audit chain visualiser */}
      {chainData && (
        <Card withBorder radius="md" p="lg">
          <Group gap="xs" mb="md">
            <ThemeIcon size={32} color={chainData.chain_valid ? "green" : "red"} variant="light" radius="md">
              <IconShieldCheck size={18} />
            </ThemeIcon>
            <Box>
              <Text fw={600}>Audit Chain Integrity</Text>
              <Text size="xs" c="dimmed">{chainData.total_entries} entries · SHA-256 hash chain</Text>
            </Box>
            <Badge color={chainData.chain_valid ? "green" : "red"} variant="filled" ml="auto">
              {chainData.chain_valid ? "✓ INTACT" : "⚠ BROKEN"}
            </Badge>
          </Group>
          <Group gap="sm" wrap="wrap">
            {chainData.nodes.slice(-8).map((node) => (
              <Badge
                key={node.id}
                size="xs"
                color={node.valid ? "green" : "red"}
                variant="light"
                ff="monospace"
              >
                #{node.id} {node.valid ? "✓" : "✗"}
              </Badge>
            ))}
            {chainData.nodes.length > 8 && (
              <Badge size="xs" color="gray" variant="outline">+{chainData.nodes.length - 8} more</Badge>
            )}
          </Group>
        </Card>
      )}
    </Stack>
  );
}

