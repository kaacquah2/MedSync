import { Button, Center, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconShieldOff } from "@tabler/icons-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";

/**
 * Shown when a user navigates to a route they don't have permission for.
 * Replaces the silent Navigate to "/" in RequireRole.
 */
export function AccessDenied() {
  const navigate = useNavigate();
  const { user } = useAuth();

  return (
    <Center h={500}>
      <Stack align="center" gap="md" maw={460} ta="center">
        <ThemeIcon size={72} radius="xl" color="danger" variant="light">
          <IconShieldOff size={40} />
        </ThemeIcon>
        <Title order={2}>Access Denied</Title>
        <Text c="dimmed" size="sm">
          Your account ({user?.role_display}) does not have permission to view
          this page. If you believe this is an error, contact your hospital
          administrator.
        </Text>
        <Button variant="light" onClick={() => navigate(-1)}>
          ← Go Back
        </Button>
      </Stack>
    </Center>
  );
}
