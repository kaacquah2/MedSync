import { BarChart, DonutChart, LineChart } from "@mantine/charts";
import { Card, Center, Stack, Text, Group } from "@mantine/core";
import {
  IconChartBar,
  IconChartDonut,
  IconChartLine,
} from "@tabler/icons-react";
import type { ChartConfig } from "@/types";

const PALETTE = [
  "medsync.5", // --accent (Brand Teal)
  "danger.5",  // --danger (Crimson Red)
  "warn.5",    // --warn (Amber Gold)
  "clinical.5",// --ok (EMR Green)
  "cyan.5",
  "violet.5",
  "orange.5",
  "green.5",
];

interface Props {
  title: string;
  chart: ChartConfig;
  h?: number;
}

/** True when every data point across all datasets is 0 (or the chart has no data). */
function isChartEmpty(chart: ChartConfig): boolean {
  if (!chart.labels.length) return true;
  return chart.datasets.every((ds) => ds.data.every((v) => v === 0));
}

function EmptyState({ title, type, h }: { title: string; type: string; h: number }) {
  const Icon =
    type === "line" ? IconChartLine :
    type === "bar"  ? IconChartBar  :
    IconChartDonut;

  return (
    <Card withBorder radius="14px" padding="lg">
      <Text className="cardTitle" mb="sm">
        {title.toLowerCase().replace(/_/g, " ")}
      </Text>
      <Center h={h}>
        <Stack align="center" gap="xs">
          <Icon size={24} style={{ color: "var(--muted)" }} />
          <Text size="sm" c="var(--muted)">
            No data yet. Activity will appear here once recorded.
          </Text>
        </Stack>
      </Center>
    </Card>
  );
}

export function ChartPanel({ title, chart, h = 220 }: Props) {
  if (isChartEmpty(chart)) {
    return <EmptyState title={title} type={chart.type} h={h} />;
  }

  const header = (
    <Group justify="space-between" mb="md" align="center">
      <Text className="cardTitle">
        {title.toLowerCase().replace(/_/g, " ")}
      </Text>
    </Group>
  );

  if (chart.type === "line") {
    const seriesData = chart.labels.map((label, i) => {
      const entry: Record<string, string | number> = { date: label };
      chart.datasets.forEach((ds, di) => {
        entry[ds.label ?? `series${di}`] = ds.data[i] ?? 0;
      });
      return entry;
    });

    const series = chart.datasets.map((ds, di) => ({
      name:  ds.label ?? `series${di}`,
      color: ds.color ? colorToCssVar(ds.color, di) : PALETTE[di % PALETTE.length],
    }));

    return (
      <Card withBorder radius="md" padding="lg">
        {header}
        <LineChart
          h={h}
          data={seriesData}
          dataKey="date"
          series={series}
          curveType="monotone"
          withDots={false}
          withLegend={series.length > 1}
          gridAxis="y"
          yAxisProps={{ allowDecimals: false }}
        />
      </Card>
    );
  }

  if (chart.type === "bar" || chart.type === "horizontal-bar") {
    const ds = chart.datasets[0];
    const barData = chart.labels.map((label, i) => ({
      label,
      value: ds?.data[i] ?? 0,
    }));

    const isHorizontal = chart.type === "horizontal-bar";

    return (
      <Card withBorder radius="md" padding="lg">
        {header}
        <BarChart
          h={h}
          data={barData}
          dataKey="label"
          series={[{ name: "value", color: PALETTE[0] }]}
          gridAxis="xy"
          barProps={{ maxBarSize: 48 }}
          orientation={isHorizontal ? "horizontal" : "vertical"}
          yAxisProps={{ allowDecimals: false }}
        />
      </Card>
    );
  }

  if (chart.type === "doughnut") {
    const ds = chart.datasets[0];
    const donutData = chart.labels.map((label, i) => ({
      name:  label,
      value: ds?.data[i] ?? 0,
      color: PALETTE[i % PALETTE.length],
    })).filter((d) => d.value > 0);

    return (
      <Card withBorder radius="md" padding="lg">
        {header}
        <DonutChart
          h={h}
          data={donutData}
          withLabelsLine
          withLabels
        />
      </Card>
    );
  }

  return null;
}

/** Convert hex colour to closest Mantine color token. */
function colorToCssVar(hex: string, index = 0): string {
  const map: Record<string, string> = {
    "#0d6efd": "medsync.5",
    "#198754": "green.6",
    "#20c997": "teal.5",
    "#dc3545": "red.6",
    "#ffc107": "yellow.5",
    "#0dcaf0": "cyan.5",
    "#6f42c1": "violet.6",
    "#fd7e14": "orange.5",
    "#1a2744": "dark.8",
  };
  return map[hex.toLowerCase()] ?? PALETTE[index % PALETTE.length];
}
