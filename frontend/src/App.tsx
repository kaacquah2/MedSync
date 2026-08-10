/**
 * App.tsx — root router for the mEd SPA.
 *
 * Routes are dynamically registered from routesConfig.ts and
 * automatically wrapped in role-based guards.
 */

import { Suspense } from "react";
import { Button, Container, LoadingOverlay, Paper, Text, Title } from "@mantine/core";
import { Link, Route, Routes } from "react-router-dom";
import { AuthProvider }    from "@/auth/AuthProvider";
import { LoginPage }       from "@/auth/LoginPage";
import { MfaSetupPage }    from "@/auth/MfaSetupPage";
import { MfaVerifyPage }   from "@/auth/MfaVerifyPage";
import { RequireAuth, RequireRole } from "@/auth/RequireAuth";
import { AppLayout }       from "@/layout/AppLayout";
import { RoleHome }      from "@/pages/common/RoleHome";
import { AccessDenied }  from "@/pages/common/AccessDenied";
import { routesConfig }   from "@/constants/routesConfig";
import { ErrorBoundary }  from "@/components/ErrorBoundary";

export function App() {
  return (
    <AuthProvider>
      <ErrorBoundary>
        <Routes>
          {/* ── Public (no auth required) ──────────────────────────────────── */}
          <Route path="/login"      element={<LoginPage />} />
          <Route path="/mfa/setup"  element={<MfaSetupPage />} />
          <Route path="/mfa/verify" element={<MfaVerifyPage />} />

          {/* ── Protected (all authenticated roles) ───────────────────────── */}
          <Route
            element={
              <RequireAuth>
                <AppLayout />
              </RequireAuth>
            }
          >
            {/* Index: role-aware redirect (super_admin→/superadmin, others→dashboard) */}
            <Route index element={<RoleHome />} />

            {/* Dynamically register all protected routes from routesConfig */}
            {routesConfig.map((route) => {
              const Component = route.element;
              return (
                <Route
                  key={route.path}
                  path={route.path}
                  element={
                    <RequireRole roles={route.roles}>
                      <ErrorBoundary>
                        <Suspense fallback={<LoadingOverlay visible zIndex={1000} overlayProps={{ radius: "sm", blur: 2 }} />}>
                          <Component />
                        </Suspense>
                      </ErrorBoundary>
                    </RequireRole>
                  }
                />
              );
            })}
          </Route>

          {/* 403 */}
          <Route path="/403" element={<AccessDenied />} />

          {/* 404 */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </ErrorBoundary>
    </AuthProvider>
  );
}

function NotFound() {
  return (
    <Container size="xs" py="xl">
      <Paper radius="md" p="xl" withBorder style={{ textAlign: "center" }}>
        <Title order={2} mb="sm">404 — Page Not Found</Title>
        <Text color="dimmed" mb="lg">The page you are looking for does not exist or has been moved.</Text>
        <Button component={Link} to="/" variant="light">
          Go to Dashboard
        </Button>
      </Paper>
    </Container>
  );
}
