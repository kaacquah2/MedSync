import {
  Alert,
  Anchor,
  Button,
  Card,
  Divider,
  Group,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { PageHeader } from "@/components/PageHeader";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle, IconCalendar, IconCheck, IconUserPlus } from "@tabler/icons-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createPatient, fetchPatient, updatePatient } from "@/api/endpoints";
import { normalizeApiError } from "@/api/client";
import { useQuery } from "@tanstack/react-query";
import type { Patient } from "@/types";

interface CreatePatientResponse {
  confirm_new_required?: boolean;
  warning?: string;
  candidates?: string[];
  universal_id?: string;
}

interface EMPIErrorResponse {
  response?: {
    data?: {
      empi_confidence?: string;
      error?: string;
    };
  };
}

const SEX_OPTIONS    = [{ value: "M", label: "Male" }, { value: "F", label: "Female" }, { value: "O", label: "Other / Prefer not to say" }];
const BLOOD_OPTIONS  = ["A+","A-","B+","B-","AB+","AB-","O+","O-","?"].map((v) => ({ value: v, label: v }));

interface FormValues {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  sex: string;
  blood_group: string;
  national_id: string;
  phone: string;
  email: string;
  address: string;
}

export function PatientFormPage() {
  const { nhid }   = useParams<{ nhid: string }>();
  const isEdit     = !!nhid;
  const navigate   = useNavigate();
  const [loading, setLoading]             = useState(false);
  const [confirmNew, setConfirmNew]        = useState(false);
  const [dupWarning, setDupWarning]        = useState<string | null>(null);
  const [dupCandidates, setDupCandidates] = useState<string[]>([]);

  const { data: existing } = useQuery({
    queryKey: ["patient", nhid],
    queryFn:  () => fetchPatient(nhid!).then((r) => r.data),
    enabled:  isEdit,
  });

  const form = useForm<FormValues>({
    initialValues: {
      first_name:    existing?.first_name    ?? "",
      last_name:     existing?.last_name     ?? "",
      date_of_birth: existing?.date_of_birth ?? "",
      sex:           existing?.sex           ?? "O",
      blood_group:   existing?.blood_group   ?? "?",
      national_id:   existing?.national_id   ?? "",
      phone:         existing?.phone         ?? "",
      email:         existing?.email         ?? "",
      address:       existing?.address       ?? "",
    },
    validate: {
      first_name:    (v) => (v.trim() ? null : "First name is required"),
      last_name:     (v) => (v.trim() ? null : "Last name is required"),
      date_of_birth: (v) => (v.trim() ? null : "Date of birth is required"),
    },
  });

  // Re-initialize when existing patient loads
  if (isEdit && existing && !form.isDirty()) {
    form.setValues({
      first_name:    existing.first_name,
      last_name:     existing.last_name,
      date_of_birth: existing.date_of_birth,
      sex:           existing.sex,
      blood_group:   existing.blood_group,
      national_id:   existing.national_id ?? "",
      phone:         existing.phone ?? "",
      email:         existing.email ?? "",
      address:       existing.address ?? "",
    });
  }

  async function handleSubmit(values: FormValues) {
    setLoading(true);
    setDupWarning(null);
    try {
      if (isEdit) {
        await updatePatient(nhid!, values as unknown as Partial<Patient>);
        notifications.show({ color: "green", icon: <IconCheck />, message: "Patient record updated." });
        navigate(`/patients/${nhid}`);
      } else {
        const res = await createPatient(values as unknown as Record<string, unknown>, confirmNew || undefined);
        const resData = res.data as CreatePatientResponse;
        if (resData.confirm_new_required) {
          setDupWarning(resData.warning as string);
          setDupCandidates(resData.candidates as string[]);
          setConfirmNew(false);
        } else {
          notifications.show({ color: "green", icon: <IconCheck />, message: `Patient registered. NHID: ${resData.universal_id}` });
          navigate(`/patients/${resData.universal_id}`);
        }
      }
    } catch (err) {
      const norm = normalizeApiError(err);
      if (norm.details) {
        form.setErrors(norm.details);
      }
      const d = (err as EMPIErrorResponse)?.response?.data;
      if (d?.empi_confidence === "exact" || d?.empi_confidence === "conflict") {
        notifications.show({ color: "red", message: d.error });
      } else {
        notifications.show({ color: "red", message: norm.message || "Failed to save patient." });
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <Stack gap="lg">
      <PageHeader
        icon={<IconUserPlus size={20} />}
        title={isEdit ? "Edit Patient" : "Register New Patient"}
        subtitle={isEdit ? `Editing record: ${nhid}` : "Register a new patient in the system"}
      />

      {dupWarning && (
        <Alert color="yellow" icon={<IconAlertCircle />} title="Possible Duplicate Detected">
          <Text size="sm">{dupWarning}</Text>
          <Text size="sm" mt="xs">
            Possible matches:{" "}
            {dupCandidates.map((id) => (
              /* Use Link for client-side navigation (no full-page reload) */
              <Anchor key={id} component={Link} to={`/patients/${id}`} ff="monospace" size="sm" mr={6}>
                {id}
              </Anchor>
            ))}
          </Text>
          <Button
            mt="sm"
            size="xs"
            color="yellow"
            onClick={() => { setConfirmNew(true); form.onSubmit(handleSubmit)(); }}
          >
            Confirm — this is a new patient
          </Button>
        </Alert>
      )}

      <Card withBorder radius="md" padding="lg">
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="md">
            <Title order={5}>Personal Information</Title>

            <Group grow>
              <TextInput label="First Name" placeholder="John" required {...form.getInputProps("first_name")} />
              <TextInput label="Last Name / Surname" placeholder="Mensah" required {...form.getInputProps("last_name")} />
            </Group>

            <Group grow>
              <DateInput
                label="Date of Birth"
                placeholder="Pick a date"
                leftSection={<IconCalendar size={16} />}
                maxDate={new Date()}
                valueFormat="DD MMM YYYY"
                required
                /* Keep form value as YYYY-MM-DD string for the API */
                value={form.values.date_of_birth ? new Date(form.values.date_of_birth + "T00:00:00") : null}
                onChange={(date) =>
                  form.setFieldValue(
                    "date_of_birth",
                    date
                      ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
                      : ""
                  )
                }
                error={form.errors.date_of_birth as string | undefined}
              />
              <Select
                label="Sex"
                data={SEX_OPTIONS}
                {...form.getInputProps("sex")}
              />
              <Select
                label="Blood Group"
                data={BLOOD_OPTIONS}
                {...form.getInputProps("blood_group")}
              />
            </Group>

            <TextInput
              label="National ID / Passport"
              placeholder="GHA-123456789"
              description="Used for EMPI duplicate detection"
              {...form.getInputProps("national_id")}
            />

            <Divider label="Contact Information" labelPosition="left" />

            <Group grow>
              <TextInput label="Phone" placeholder="+233 20 123 4567" {...form.getInputProps("phone")} />
              <TextInput label="Email" placeholder="patient@example.com" {...form.getInputProps("email")} />
            </Group>

            <Textarea label="Address" placeholder="Street, City, Region" rows={3} {...form.getInputProps("address")} />

            <Group justify="flex-end" mt="md">
              <Button variant="subtle" onClick={() => navigate(-1)}>Cancel</Button>
              <Button
                type="submit"
                loading={loading}
                leftSection={<IconUserPlus size={16} />}
              >
                {isEdit ? "Save Changes" : "Register Patient"}
              </Button>
            </Group>
          </Stack>
        </form>
      </Card>
    </Stack>
  );
}
