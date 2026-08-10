import {
  Button,
  Card,
  Group,
  Select,
  Stack,
  Textarea,
  TextInput,
} from "@mantine/core";
import { PageHeader } from "@/components/PageHeader";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconCheck } from "@tabler/icons-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createAlert } from "@/api/endpoints";
import { normalizeApiError } from "@/api/client";

export function AlertFormPage() {
  const { nhid }   = useParams<{ nhid: string }>();
  const navigate   = useNavigate();
  const [loading, setLoading] = useState(false);

  const form = useForm({
    initialValues: {
      kind:     "ALLERGY" as "ALLERGY" | "ALERT",
      label:    "",
      severity: "MODERATE" as "MILD" | "MODERATE" | "SEVERE" | "LIFE_THREAT",
      reaction: "",
    },
    validate: {
      label: (v) => (v.trim() ? null : "Substance / description is required"),
    },
  });

  async function handleSubmit(values: typeof form.values) {
    setLoading(true);
    try {
      await createAlert(nhid!, values);
      notifications.show({ color: "green", icon: <IconCheck />, message: "Alert recorded." });
      navigate(`/patients/${nhid}`);
    } catch (err) {
      const norm = normalizeApiError(err);
      if (norm.details) form.setErrors(norm.details);
      notifications.show({ color: "red", message: norm.message || "Failed to create alert." });
    } finally {
      setLoading(false);
    }
  }

  return (
    <Stack gap="lg">
      <PageHeader
        icon={<IconAlertTriangle size={20} />}
        title="Record Alert / Allergy"
        subtitle={`Patient: ${nhid}`}
      />
      <Card withBorder radius="md" padding="lg">
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="md">
            <Select
              label="Type"
              data={[{ value: "ALLERGY", label: "Allergy" }, { value: "ALERT", label: "Clinical Alert" }]}
              {...form.getInputProps("kind")}
            />
            <TextInput
              label="Substance / Description"
              placeholder="e.g. Penicillin, Latex, Peanuts, Contrast dye…"
              required
              {...form.getInputProps("label")}
            />
            <Select
              label="Severity"
              data={[
                { value: "MILD",        label: "Mild" },
                { value: "MODERATE",    label: "Moderate" },
                { value: "SEVERE",      label: "Severe" },
                { value: "LIFE_THREAT", label: "Life-threatening" },
              ]}
              {...form.getInputProps("severity")}
            />
            <Textarea
              label="Reaction Notes"
              placeholder="Describe the observed reaction (optional)…"
              rows={3}
              {...form.getInputProps("reaction")}
            />
            <Group justify="flex-end" mt="md">
              <Button variant="subtle" onClick={() => navigate(`/patients/${nhid}`)}>Cancel</Button>
              <Button
                type="submit"
                loading={loading}
                leftSection={<IconAlertTriangle size={16} />}
                color="orange"
              >
                Record Alert
              </Button>
            </Group>
          </Stack>
        </form>
      </Card>
    </Stack>
  );
}
