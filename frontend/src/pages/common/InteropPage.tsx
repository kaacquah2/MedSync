import {
  Badge,
  Box,
  Card,
  Code,
  Group,
  List,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconArrowLeftRight,
  IconDatabase,
  IconFingerprint,
  IconLock,
  IconShieldLock,
  IconUserCheck,
} from "@tabler/icons-react";
import { useAuth } from "@/auth/AuthProvider";

export function InteropPage() {
  const { user } = useAuth();

  return (
    <Stack gap="lg">
      {/* Header */}
      <Group gap="xs">
        <ThemeIcon size={36} color="indigo" variant="light" radius="md">
          <IconArrowLeftRight size={20} />
        </ThemeIcon>
        <Box>
          <Title order={2}>Inter-Hospital Consent & Security</Title>
          <Text size="xs" c="dimmed">
            Under the hood: cryptographically enforcing patient privacy and audit compliance
          </Text>
        </Box>
      </Group>

      {/* Pillar Cards */}
      <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
        <Card withBorder radius="md" p="md">
          <ThemeIcon size={40} radius="md" color="blue" variant="light" mb="sm">
            <IconLock size={20} />
          </ThemeIcon>
          <Text fw={700} size="md" mb={6}>Application-Layer Encryption</Text>
          <Text size="xs" c="dimmed" lh={1.4}>
            All Personally Identifiable Information (PII) and Protected Health Information (PHI) is encrypted
            using symmetric <strong>Fernet (AES-128-CBC + HMAC-SHA256)</strong> before it hits the database.
            Even DB administrators or cloud providers cannot see patient records in plaintext.
          </Text>
        </Card>

        <Card withBorder radius="md" p="md">
          <ThemeIcon size={40} radius="md" color="violet" variant="light" mb="sm">
            <IconFingerprint size={20} />
          </ThemeIcon>
          <Text fw={700} size="md" mb={6}>HMAC-SHA256 Blind Indexing</Text>
          <Text size="xs" c="dimmed" lh={1.4}>
            To allow fast patient lookups by name or National ID without decrypting every row in memory, the system uses
            keyed <strong>HMAC-SHA256 hashes (Blind Indexes)</strong>. Searches perform exact-match checks on hashes
            without ever exposing the underlying plaintext.
          </Text>
        </Card>

        <Card withBorder radius="md" p="md">
          <ThemeIcon size={40} radius="md" color="indigo" variant="light" mb="sm">
            <IconShieldLock size={20} />
          </ThemeIcon>
          <Text fw={700} size="md" mb={6}>Cryptographic Audit Trail</Text>
          <Text size="xs" c="dimmed" lh={1.4}>
            Every database read/write generates a signed audit entry. These entries are cryptographically chained
            together using **SHA-256 hash chaining** (similar to block structures). If any log entry is altered,
            the validation check immediately fails.
          </Text>
        </Card>
      </SimpleGrid>

      {/* Security Policies */}
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg" mt="md">
        <Card withBorder radius="md" p="lg">
          <Group gap="xs" mb="md">
            <ThemeIcon color="green" radius="sm" size={26}>
              <IconUserCheck size={16} />
            </ThemeIcon>
            <Text fw={700}>Patient Sharing Consent Rules</Text>
          </Group>

          <Stack gap="sm">
            <Box>
              <Badge color="green" variant="light" mb={4}>Same-Hospital Access</Badge>
              <Text size="xs" c="dimmed" lh={1.4}>
                Clinicians are automatically authorized to access any patient registered at their home hospital.
              </Text>
            </Box>
            <Box>
              <Badge color="blue" variant="light" mb={4}>Treatment Relationships</Badge>
              <Text size="xs" c="dimmed" lh={1.4}>
                When a doctor creates an encounter or prescription for an external patient, a 30-day care relationship is
                established. This grants the clinician full chart access for ongoing treatment.
              </Text>
            </Box>
            <Box>
              <Badge color="orange" variant="light" mb={4}>Emergency Break-Glass</Badge>
              <Text size="xs" c="dimmed" lh={1.4}>
                In critical emergencies, clinicians can request temporary 1-hour access. This override requires a written
                justification and is automatically flagged for super-admin review.
              </Text>
            </Box>
          </Stack>
        </Card>

        <Card withBorder radius="md" p="lg">
          <Group gap="xs" mb="md">
            <ThemeIcon color="violet" radius="sm" size={26}>
              <IconDatabase size={16} />
            </ThemeIcon>
            <Text fw={700}>System Configuration</Text>
          </Group>

          <Stack gap="md">
            <Box>
              <Text size="sm" fw={600} mb={4}>Active Hospital Node</Text>
              <Code block color="indigo" style={{ fontSize: "11px" }}>
                Hospital: {user?.hospital?.name ?? "N/A (Central Node)"}
                {"\n"}Code: {user?.hospital?.code ?? "SYSTEM_ADMIN"}
                {"\n"}Role Scope: {user?.role}
              </Code>
            </Box>

            <Box>
              <Text size="sm" fw={600} mb={4}>Core Cryptographic Algorithms</Text>
              <List size="xs" c="dimmed" spacing={4}>
                <List.Item>Symmetric Field Cipher: AES-128-CBC + HMAC-SHA256 (Fernet)</List.Item>
                <List.Item>Search hashing: HMAC-SHA256 (Normalised case-insensitive)</List.Item>
                <List.Item>Audit verification chain: SHA-256 backlink chaining</List.Item>
                <List.Item>Network inter-hospital TLS: Forced sslmode=require</List.Item>
              </List>
            </Box>
          </Stack>
        </Card>
      </SimpleGrid>
    </Stack>
  );
}
