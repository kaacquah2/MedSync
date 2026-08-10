/**
 * EmptyState — standardised empty content placeholder used across all pages.
 *
 * Replaces three different ad-hoc patterns:
 *   • .empty-state CSS class (ReportsPage)
 *   • Center + Stack + icon (ChartPanel, AnalyticsPage, EmergencyQueuePage)
 *   • bare <Text c="dimmed"> (PatientDetailPage tabs)
 *
 * Usage:
 *   <EmptyState icon={<IconSearch size={28} />} title="No patients found"
 *     description="Try a different search term." />
 *
 *   <EmptyState icon={<IconFlask size={28} />} title="No lab results"
 *     action={<Button size="xs">Order test</Button>} />
 */

import { Center, Stack, Text, ThemeIcon } from "@mantine/core";
import type { ReactNode } from "react";

interface EmptyStateProps {
  /** Tabler icon element to display (e.g. <IconSearch size={28} />) */
  icon: ReactNode;
  /** Short heading text */
  title: string;
  /** Optional secondary description sentence */
  description?: string;
  /** Optional call-to-action (Button, Link, etc.) */
  action?: ReactNode;
  /** Wrapper height (default 200px) */
  height?: number | string;
  /** Color of the icon ThemeIcon (default "gray") */
  color?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  height = 200,
  color = "gray",
}: EmptyStateProps) {
  return (
    <Center h={height} py="xl">
      <Stack align="center" gap="sm" maw={300} ta="center">
        <ThemeIcon size={52} radius="xl" color={color} variant="light">
          {icon}
        </ThemeIcon>
        <Text fw={600} size="sm" c="dimmed">
          {title}
        </Text>
        {description && (
          <Text size="xs" c="dimmed" lh={1.5}>
            {description}
          </Text>
        )}
        {action}
      </Stack>
    </Center>
  );
}
