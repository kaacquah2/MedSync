import {
  Anchor,
  Badge,
  Box,
  Card,
  Group,
  Indicator,
  Skeleton,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconAlertTriangle, IconBell, IconFlask } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { Link } from "react-router-dom";
import { fetchAlerts } from "@/api/endpoints";
import type { AlertFeedItem } from "@/types";

dayjs.extend(relativeTime);

const SEVERITY_COLORS: Record<AlertFeedItem["severity"], string> = {
  LIFE_THREAT: "red",
  SEVERE:      "red",
  MODERATE:    "orange",
  MILD:        "yellow",
};

const KIND_ICONS: Record<string, React.ReactNode> = {
  LAB_ABNORMAL: <IconFlask size={18} />,
  ALLERGY:      <IconAlertTriangle size={18} />,
  ALERT:        <IconBell size={18} />,
};

export function AlertsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => fetchAlerts().then((r) => r.data),
    refetchInterval: 30_000,
  });

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="red" variant="light" radius="md">
            <IconBell size={20} />
          </ThemeIcon>
          <Box>
            <Title order={2}>Alerts Feed</Title>
            <Text c="dimmed" size="xs">
              {data ? `${data.count} active alert${data.count !== 1 ? "s" : ""}` : "Loading…"}
            </Text>
          </Box>
        </Group>
      </Group>

      {isLoading ? (
        <Stack gap="sm">
          {[1, 2, 3].map((i) => <Skeleton key={i} height={80} radius="md" />)}
        </Stack>
      ) : !data?.results.length ? (
        <Card withBorder p="xl" ta="center">
          <ThemeIcon size={48} color="green" variant="light" radius="xl" mx="auto" mb="md">
            <IconBell size={28} />
          </ThemeIcon>
          <Text fw={600}>No active alerts</Text>
          <Text c="dimmed" size="sm">All clear — no critical alerts in your scope.</Text>
        </Card>
      ) : (
        <Stack gap="sm">
          {data.results.map((alert) => (
            <AlertCard key={alert.id} alert={alert} />
          ))}
        </Stack>
      )}
    </Stack>
  );
}

function AlertCard({ alert }: { alert: AlertFeedItem }) {
  const color = SEVERITY_COLORS[alert.severity];
  const isHighPriority = alert.severity === "LIFE_THREAT" || alert.severity === "SEVERE";

  return (
    <Card
      withBorder
      radius="md"
      p="md"
      style={{
        borderLeftWidth: 4,
        borderLeftColor: `var(--mantine-color-${color}-6)`,
      }}
    >
      <Group justify="space-between" align="flex-start">
        <Group gap="sm" align="flex-start">
          <Indicator
            color={color}
            processing={isHighPriority}
            size={8}
            offset={4}
          >
            <ThemeIcon size={36} color={color} variant="light" radius="md">
              {KIND_ICONS[alert.kind] ?? <IconAlertTriangle size={18} />}
            </ThemeIcon>
          </Indicator>

          <Box>
            <Group gap="xs" mb={2}>
              <Text fw={600} size="sm">{alert.label}</Text>
              <Badge color={color} size="xs" variant="filled">
                {alert.severity.replace("_", " ")}
              </Badge>
            </Group>
            {alert.detail && (
              <Text size="xs" c="dimmed" lineClamp={2}>{alert.detail}</Text>
            )}
            {alert.patient_nhid && (
              <Group gap={4} mt={4}>
                <Text size="xs" c="dimmed">Patient:</Text>
                <Anchor
                  component={Link}
                  to={`/patients/${alert.patient_nhid}`}
                  size="xs"
                  fw={500}
                >
                  {alert.patient_name ?? alert.patient_nhid}
                </Anchor>
                <Text size="xs" c="dimmed" ff="monospace">({alert.patient_nhid})</Text>
              </Group>
            )}
          </Box>
        </Group>

        <Text size="xs" c="dimmed">{dayjs(alert.timestamp).fromNow()}</Text>
      </Group>
    </Card>
  );
}
