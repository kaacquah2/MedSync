/**
 * PageHeader — standardised page-level header used across all role pages.
 *
 * Layout:
 *   [ThemeIcon] [Title + optional subtitle]       [actions slot]
 *
 * Usage:
 *   <PageHeader icon={<IconUsers />} title="Staff Management" />
 *   <PageHeader icon={<IconUsers />} title="Staff Management" subtitle="UGMC · 12 staff">
 *     <Button>Add Staff</Button>
 *   </PageHeader>
 */

import { Box, Group, Text, ThemeIcon, Title } from "@mantine/core";
import type { ReactNode } from "react";

interface PageHeaderProps {
  /** Tabler icon element (e.g. <IconUsers size={20} />) */
  icon: ReactNode;
  /** Page / section title */
  title: string;
  /** Optional dimmed subtitle below the title */
  subtitle?: string;
  /** Optional right-side actions (buttons, menus, etc.) */
  children?: ReactNode;
}

export function PageHeader({ icon, title, subtitle, children }: PageHeaderProps) {
  return (
    <Group justify="space-between" wrap="nowrap">
      <Group gap="sm">
        <ThemeIcon size={36} color="medsync" variant="light" radius="md">
          {icon}
        </ThemeIcon>
        <Box>
          <Title order={2} lh={1.2}>{title}</Title>
          {subtitle && (
            <Text size="sm" c="dimmed" mt={2}>{subtitle}</Text>
          )}
        </Box>
      </Group>
      {children && (
        <Group gap="xs" wrap="nowrap">
          {children}
        </Group>
      )}
    </Group>
  );
}
