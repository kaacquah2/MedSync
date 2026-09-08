import {
  Anchor,
  Badge,
  Button,
  Group,
  Pagination,
  Paper,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import {
  IconArrowRight,
  IconSearch,
  IconShield,
  IconUserPlus,
} from "@tabler/icons-react";
import { PageHeader } from "@/components/PageHeader";
import { DataStateWrapper } from "@/components/DataStateWrapper";
import { queryKeys } from "@/api/queryKeys";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState, useEffect } from "react";
import { Link, useNavigate, useLocation, useSearchParams } from "react-router-dom";
import { searchPatients } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";

const SEX_LABEL: Record<string, string> = { M: "Male", F: "Female", O: "Other" };

/** Must match the DRF page_size setting in emr/settings.py */
const PAGE_SIZE = 20;

export function PatientSearchPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const { user } = useAuth();

  // Read initial query from navigation state or URL param (which we sanitize immediately)
  const queryParam = params.get("q");
  const navStateQ = (location.state as { q?: string } | null)?.q;
  const initialQ = navStateQ ?? queryParam ?? "";

  const [q, setQ] = useState(initialQ);
  const [activeQ, setActiveQ] = useState(initialQ);
  const [page, setPage] = useState(1);

  // If a sensitive search query was passed in the URL query string, sanitize the URL immediately
  // to avoid leaving patient identifiers in the address bar / browser history
  useEffect(() => {
    if (queryParam) {
      navigate("/patients", { replace: true, state: { q: queryParam } });
    }
  }, [queryParam, navigate]);

  // Synchronize when global navbar search pushes new search state to /patients
  useEffect(() => {
    const navQ = (location.state as { q?: string } | null)?.q;
    if (navQ !== undefined && navQ !== activeQ) {
      setQ(navQ);
      setActiveQ(navQ);
      setPage(1);
    }
  }, [location.state, activeQ]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: queryKeys.patients(user?.hospital?.id, user?.id, activeQ, page),
    queryFn:  () => searchPatients(activeQ, page).then((r) => r.data),
    enabled:  true,
    staleTime: 30_000,
  });

  function doSearch(e: React.FormEvent) {
    e.preventDefault();
    const cleanQ = q.trim();
    if (/^NHID-[A-F0-9]{8,16}$/i.test(cleanQ)) {
      // Direct route navigation to avoid leaving sensitive patient NHIDs in URL query strings
      navigate(`/patients/${cleanQ.toUpperCase()}`);
      return;
    }
    setPage(1);
    setActiveQ(cleanQ);
  }

  const canRegister = ["doctor", "nurse", "receptionist", "hospital_admin", "super_admin"].includes(
    user?.role ?? ""
  );

  const totalPages = data ? Math.ceil(data.count / PAGE_SIZE) : 1;

  return (
    <Stack gap="lg">
      <PageHeader icon={<IconSearch size={20} />} title="Patient Search">
        {canRegister && (
          <Button
            component={Link}
            to="/patients/new"
            leftSection={<IconUserPlus size={16} />}
          >
            Register Patient
          </Button>
        )}
      </PageHeader>

      {/* Search form */}
      <Paper withBorder p="md" radius="md">
        <form onSubmit={doSearch}>
          <Group>
            <TextInput
              placeholder="Search by name, NHID, or national ID…"
              leftSection={<IconSearch size={16} />}
              value={q}
              onChange={(e) => setQ(e.currentTarget.value)}
              style={{ flex: 1 }}
              autoFocus
            />
            <Button type="submit" loading={isLoading}>Search</Button>
          </Group>
        </form>
        <Text size="xs" c="dimmed" mt="xs">
          Tip: enter a full name, NHID-XXXXXXXX, or national ID number for best results.
        </Text>
      </Paper>

      {/* Results */}
      <DataStateWrapper
        isLoading={isLoading}
        error={error}
        isEmpty={!!data && data.results.length === 0}
        emptyTitle="No Patients Found"
        emptyMessage={activeQ ? `No patient matches search query "${activeQ}".` : "No registered patients found."}
        onRetry={() => void refetch()}
      >
        {data && (
          <>
            <Text size="sm" c="dimmed">
              Found {data.count} patient{data.count !== 1 ? "s" : ""}
            </Text>

            <Table.ScrollContainer minWidth={800}>
              <Table striped highlightOnHover withTableBorder withColumnBorders>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>NHID</Table.Th>
                    <Table.Th>Name</Table.Th>
                    <Table.Th>DOB</Table.Th>
                    <Table.Th>Sex</Table.Th>
                    <Table.Th>Blood Group</Table.Th>
                    <Table.Th>Hospital</Table.Th>
                    <Table.Th>Reg. Date</Table.Th>
                    <Table.Th aria-label="Actions" style={{ width: 64 }}></Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.results.map((p) => (
                    <Table.Tr key={p.universal_id}>
                      <Table.Td>
                        <Text size="sm" ff="monospace" fw={600}>{p.universal_id}</Text>
                      </Table.Td>
                      <Table.Td>
                        {p.has_access === false ? (
                          <Badge color="gray" variant="light" size="sm">
                            Restricted (Other Hospital)
                          </Badge>
                        ) : (
                          <Anchor component={Link} to={`/patients/${p.universal_id}`} size="sm" fw={500}>
                            {p.full_name}
                          </Anchor>
                        )}
                      </Table.Td>
                      <Table.Td>{p.date_of_birth ?? "—"}</Table.Td>
                      <Table.Td>{p.sex ? (SEX_LABEL[p.sex] ?? p.sex) : "—"}</Table.Td>
                      <Table.Td>
                        {p.blood_group ? (
                          <Badge variant="light" size="sm">{p.blood_group}</Badge>
                        ) : (
                          "—"
                        )}
                      </Table.Td>
                      <Table.Td>{p.registered_at_hospital?.name ?? "—"}</Table.Td>
                      <Table.Td>{p.created_at ? dayjs(p.created_at).format("DD MMM YYYY") : "—"}</Table.Td>
                      <Table.Td>
                        <Button
                          component={Link}
                          to={`/patients/${p.universal_id}`}
                          size="xs"
                          variant={p.has_access === false ? "light" : "subtle"}
                          color={p.has_access === false ? "orange" : "blue"}
                          rightSection={p.has_access === false ? <IconShield size={14} /> : <IconArrowRight size={14} />}
                        >
                          {p.has_access === false ? "Request Access" : "View"}
                        </Button>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>

            {totalPages > 1 && (
              <Pagination
                total={totalPages}
                value={page}
                onChange={(p) => {
                  setPage(p);
                }}
              />
            )}
          </>
        )}
      </DataStateWrapper>
    </Stack>
  );
}
