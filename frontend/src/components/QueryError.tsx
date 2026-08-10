import { Alert, Button } from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";

interface QueryErrorProps {
  message?: string;
  onRetry?: () => void;
}

export function QueryError({ message = "Failed to load data.", onRetry }: QueryErrorProps) {
  return (
    <Alert
      icon={<IconAlertCircle size={20} />}
      title="Error"
      color="red"
      variant="light"
    >
      {message}
      {onRetry && (
        <Button size="xs" variant="subtle" color="red" ml="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </Alert>
  );
}
