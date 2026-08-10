import type { Role } from "@/types";
import { routesConfig } from "@/constants/routesConfig";

export interface NavItem {
  label: string;
  path: string;
  icon: string;   // Tabler icon name
  end?: boolean;  // exact match for NavLink
}

export interface NavSection {
  section: string;
  items: NavItem[];
}

export const NAV_BY_ROLE: Record<Role, NavSection[]> = (() => {
  const roles: Role[] = ["super_admin", "hospital_admin", "doctor", "nurse", "lab_technician", "receptionist"];
  const result = {} as Record<Role, NavSection[]>;

  for (const role of roles) {
    const sections: NavSection[] = [];
    const sectionMap = new Map<string, NavItem[]>();

    // For non-superadmin roles, the "/" path is their home/dashboard
    if (role !== "super_admin") {
      const dashboardSection = 
        role === "doctor" ? "CLINICAL" :
        role === "nurse" ? "WARD" :
        role === "lab_technician" ? "LABORATORY" :
        role === "receptionist" ? "FRONT DESK" :
        "OVERVIEW"; // hospital_admin

      const dashboardItem: NavItem = {
        label: "Dashboard",
        path: "/",
        icon: "IconLayoutDashboard",
        end: true,
      };

      sectionMap.set(dashboardSection, [dashboardItem]);
    }

    for (const route of routesConfig) {
      if (route.roles.includes(role) && route.nav && route.nav[role]) {
        const navConf = route.nav[role]!;
        let path = route.path;
        if (!path.startsWith("/")) {
          path = "/" + path;
        }

        const item: NavItem = {
          label: navConf.label,
          path: path,
          icon: navConf.icon,
          end: route.end,
        };

        if (!sectionMap.has(navConf.section)) {
          sectionMap.set(navConf.section, []);
        }
        sectionMap.get(navConf.section)!.push(item);
      }
    }

    const sectionOrder = 
      role === "super_admin" ? ["OVERVIEW", "HOSPITALS", "SECURITY", "CONFIGURATION"] :
      role === "hospital_admin" ? ["OVERVIEW", "STAFF", "FACILITY", "MONITORING"] :
      role === "doctor" ? ["CLINICAL", "PATIENTS", "NETWORK", "ALERTS"] :
      role === "nurse" ? ["WARD", "CLINICAL", "SHIFTS", "ALERTS"] :
      role === "lab_technician" ? ["LABORATORY"] :
      role === "receptionist" ? ["FRONT DESK"] :
      [];

    for (const secName of sectionOrder) {
      const items = sectionMap.get(secName);
      if (items && items.length > 0) {
        sections.push({
          section: secName,
          items,
        });
      }
    }

    result[role] = sections;
  }

  return result;
})();
