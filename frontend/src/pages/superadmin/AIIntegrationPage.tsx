/**
 * AI Integration admin page — provider health, access control, usage stats.
 * Available to super_admin only.
 */

import {
  Alert,
  Badge,
  Box,
  Card,
  Code,
  Divider,
  Group,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconActivity, IconBolt, IconInfoCircle, IconShieldCheck } from "@tabler/icons-react";

export function AIIntegrationPage() {
  return (
    <Stack gap="lg">
      <Group gap="xs">
        <ThemeIcon size={36} color="medsync" variant="light" radius="md">
          <IconActivity size={20} />
        </ThemeIcon>
        <Title order={2}>AI Integration</Title>
      </Group>

      <Alert color="medsync" icon={<IconInfoCircle />} title="AI Clinical Decision Support">
        MedSync integrates a grounded AI assistant that answers clinician questions
        exclusively from authorised patient records. All queries are logged in the
        immutable audit trail.
      </Alert>

      {/* Provider status */}
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        <Card withBorder radius="md" p="lg">
          <Group justify="space-between" mb="md">
            <Group gap="sm">
              <ThemeIcon size={32} color="green" variant="light" radius="md">
                <IconShieldCheck size={18} />
              </ThemeIcon>
              <Text fw={700}>Local Ollama (Zero Egress)</Text>
            </Group>
            <Badge color="green" variant="light">Production Default</Badge>
          </Group>
          <Stack gap="xs">
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Recommended model</Text>
              <Code>llama3.1:8b</Code>
            </Group>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">PHI leaves server?</Text>
              <Badge color="green" size="sm" variant="light">No — fully local</Badge>
            </Group>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Compliance</Text>
              <Text size="sm" fw={500} c="green">HIPAA / Ghana DPA 2012</Text>
            </Group>
            <Divider my="xs" />
            <Text size="xs" c="dimmed">
              Set <Code>AI_PROVIDER=ollama</Code> and run Ollama locally.
              Required for production deployments — all clinical notes and records remain strictly on premise.
            </Text>
          </Stack>
        </Card>

        <Card withBorder radius="md" p="lg">
          <Group justify="space-between" mb="md">
            <Group gap="sm">
              <ThemeIcon size={32} color="orange" variant="light" radius="md">
                <IconBolt size={18} />
              </ThemeIcon>
              <Text fw={700}>Google Gemini 2.5 Flash</Text>
            </Group>
            <Badge color="yellow" variant="light">Dev / Testing Only</Badge>
          </Group>
          <Stack gap="xs">
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Tier</Text>
              <Text size="sm" fw={500}>Cloud API (DEBUG=True only)</Text>
            </Group>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Model</Text>
              <Code>gemini-2.5-flash</Code>
            </Group>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">PHI leaves server?</Text>
              <Badge color="red" size="sm" variant="light">Yes — External Egress</Badge>
            </Group>
            <Divider my="xs" />
            <Text size="xs" c="dimmed">
              For local development only. Blocked in production (<Code>DEBUG=False</Code>) because
              the free API has no BAA/DPA and clinical narrative egress violates data protection regulations.
            </Text>
          </Stack>
        </Card>
      </SimpleGrid>

      {/* Access control matrix */}
      <Card withBorder radius="md" p="lg">
        <Text fw={700} mb="md">AI Access Control Matrix</Text>
        <Stack gap="xs">
          {[
            ["Doctor",          "doctor",          "Full access — can query any authorised patient"],
            ["Nurse",           "nurse",            "Full access — can query any authorised patient"],
            ["Hospital Admin",  "hospital_admin",   "Full access — system overview queries"],
            ["Super Admin",     "super_admin",       "Full access — system-wide queries"],
            ["Lab Technician",  "lab_technician",    "No access — lab results are directly visible"],
            ["Receptionist",    "receptionist",      "No access — clinical records not in scope"],
          ].map(([role, code, note]) => (
            <Group key={code} justify="space-between" py="xs" style={{ borderBottom: "1px solid var(--mantine-color-default-border)" }}>
              <Box>
                <Text size="sm" fw={500}>{role}</Text>
                <Text size="xs" c="dimmed">{note}</Text>
              </Box>
              <Badge
                color={["doctor","nurse","hospital_admin","super_admin"].includes(code) ? "green" : "red"}
                variant="light"
                size="sm"
              >
                {["doctor","nurse","hospital_admin","super_admin"].includes(code) ? "Allowed" : "Denied"}
              </Badge>
            </Group>
          ))}
        </Stack>
      </Card>

      {/* Guardrails */}
      <Card withBorder radius="md" p="lg">
        <Text fw={700} mb="md">Safety Guardrails</Text>
        <Stack gap="sm">
          {[
            ["Grounded responses", "Model answers ONLY from authorised patient records. External knowledge is not used."],
            ["Inline citations",   "Every claim must cite a specific record (e.g. [Encounter 1], [Lab Result 2])."],
            ["Access gate",        "Patient access decision (same_hospital / treatment_relationship / break_glass) is enforced before context is built."],
            ["Full audit trail",   "Every AI query is logged as AI_QUERY in the immutable audit chain with question, provider, model, and context size."],
            ["Question limits",    "Maximum 500 characters per question. Rate limiting applies."],
          ].map(([title, desc]) => (
            <Group key={title as string} gap="sm" align="flex-start">
              <ThemeIcon size={20} color="green" variant="light" radius="xl" mt={2}>
                <IconShieldCheck size={12} />
              </ThemeIcon>
              <Box>
                <Text size="sm" fw={600}>{title}</Text>
                <Text size="xs" c="dimmed">{desc}</Text>
              </Box>
            </Group>
          ))}
        </Stack>
      </Card>
    </Stack>
  );
}
