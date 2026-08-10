import React, { Suspense } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { roleHome } from "@/constants/roles";
import { LoadingOverlay } from "@mantine/core";

const DashboardPage = React.lazy(() => import("@/pages/dashboard/DashboardPage").then((m) => ({ default: m.DashboardPage })));

/**
 * Index-route component — redirects user based on role landing route,
 * or renders the shared dashboard if roleHome returns "/".
 */
export function RoleHome() {
  const { user } = useAuth();
  if (!user) return null;

  const homePath = roleHome(user.role);
  if (homePath !== "/") {
    return <Navigate to={homePath} replace />;
  }
  return (
    <Suspense fallback={<LoadingOverlay visible zIndex={1000} overlayProps={{ radius: "sm", blur: 2 }} />}>
      <DashboardPage />
    </Suspense>
  );
}
