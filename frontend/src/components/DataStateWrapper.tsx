import React from "react";
import { Alert, Button, Center, Loader, Paper, Stack, Text, Title } from "@mantine/core";
import { IconAlertTriangle, IconDatabaseOff, IconRefresh } from "@tabler/icons-react";
import { normalizeApiError } from "@/api/client";

interface DataStateWrapperProps {
  isLoading?: boolean;
  error?: unknown;
  isEmpty?: boolean;
  emptyTitle?: string;
  emptyMessage?: string;
  onRetry?: () => void;
  children: React.ReactNode;
}

export function DataStateWrapper({
  isLoading,
  error,
  isEmpty,
  emptyTitle = "No data available",
  emptyMessage = "There are no records to display at this time.",
  onRetry,
  children,
}: DataStateWrapperProps) {
  if (isLoading) {
    return (
      <Center py="xl">
        <Loader size="lg" color="medsync" />
      </Center>
    );
  }

  if (error) {
    const norm = normalizeApiError(error);
    return (
      <Alert
        color="red"
        variant="light"
        title="Error loading data"
        icon={<IconAlertTriangle size={20} />}
        radius="md"
        my="md"
      >
        <Stack gap="xs">
          <Text size="sm">{norm.message}</Text>
          {onRetry && (
            <Button
              size="xs"
              color="red"
              variant="outline"
              leftSection={<IconRefresh size={14} />}
              onClick={onRetry}
              style={{ width: "fit-content" }}
            >
              Retry
            </Button>
          )}
        </Stack>
      </Alert>
    );
  }

  if (isEmpty) {
    return (
      <Paper p="xl" radius="md" withBorder style={{ textAlign: "center" }} my="md">
        <Center mb="sm">
          <IconDatabaseOff size={36} style={{ color: "var(--mantine-color-dimmed)" }} />
        </Center>
        <Title order={4} mb="xs">
          {emptyTitle}
        </Title>
        <Text size="sm" c="dimmed">
          {emptyMessage}
        </Text>
      </Paper>
    );
  }

  return <>{children}</>;
}
