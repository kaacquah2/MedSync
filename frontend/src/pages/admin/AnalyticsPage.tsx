import {
  Card,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
  Box,
  Group,
  Skeleton,
  Center,
} from "@mantine/core";
import { IconPresentationAnalytics } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { fetchDashboard } from "@/api/endpoints";
import { ChartPanel } from "@/pages/dashboard/ChartPanel";

export function AnalyticsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["analytics-dashboard"],
    queryFn: () => fetchDashboard().then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const charts = data?.charts ? Object.entries(data.charts) : [];
  const stats = data?.stats ?? [];

  return (
    <Stack gap="lg">
      {/* Header */}
      <Group gap="xs">
        <ThemeIcon size={36} color="medsync" variant="light" radius="md">
          <IconPresentationAnalytics size={20} />
        </ThemeIcon>
        <Box>
          <Title order={2} style={{ fontSize: "20px", fontWeight: 500 }}>Advanced Analytics</Title>
          <Text size="xs" c="dimmed">
            Live dashboard metrics for your role — reflects current activity
          </Text>
        </Box>
      </Group>

      {/* Live KPI Cards from dashboard API */}
      {isLoading ? (
        <SimpleGrid cols={{ base: 1, sm: 4 }} spacing="md">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} height={80} radius="md" />)}
        </SimpleGrid>
      ) : stats.length > 0 ? (
        <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
          {stats.map((s, i) => (
            <Card key={i} withBorder radius="md" p="md" bg="var(--surface-2)">
              <Text size="xs" tt="uppercase" fw={700} c="dimmed">{s.label}</Text>
              <Text size="xl" fw={800}>{s.value}</Text>
              {s.delta && <Text size="xs" c="dimmed" mt={4}>{s.delta}</Text>}
            </Card>
          ))}
        </SimpleGrid>
      ) : null}

      {/* Charts from dashboard API */}
      {isLoading ? (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          {[1, 2].map((i) => <Skeleton key={i} height={260} radius="md" />)}
        </SimpleGrid>
      ) : charts.length > 0 ? (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          {charts.map(([key, chart]) => (
            <ChartPanel key={key} title={key} chart={chart} />
          ))}
        </SimpleGrid>
      ) : (
        <Card withBorder radius="md" p="xl" bg="var(--surface-2)">
          <Center>
            <Stack align="center" gap="xs">
              <IconPresentationAnalytics size={40} color="var(--mantine-color-gray-4)" />
              <Text fw={500} c="dimmed">No analytics data available yet</Text>
              <Text size="xs" c="dimmed" ta="center" maw={300}>
                Charts will appear here once clinical activity is recorded. Seed the database or record encounters to see live data.
              </Text>
            </Stack>
          </Center>
        </Card>
      )}
    </Stack>
  );
}
