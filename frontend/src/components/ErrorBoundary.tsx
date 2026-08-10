import { Alert, Button, Stack, Text } from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("Render error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <Stack p="md">
          <Alert
            icon={<IconAlertCircle size={20} />}
            title="Something went wrong"
            color="red"
            variant="light"
          >
            <Text size="sm" mb="xs">{this.state.error.message}</Text>
            <Button
              size="xs"
              variant="light"
              color="red"
              onClick={() => this.setState({ error: null })}
            >
              Try again
            </Button>
          </Alert>
        </Stack>
      );
    }
    return this.props.children;
  }
}
