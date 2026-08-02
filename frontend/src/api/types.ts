export type AccountRole = "USER" | "SYSTEM_OWNER" | "ADMIN";
export type AccountStatus = "ACTIVE" | "DISABLED";
export type AccountSource = "LOCAL_IMPORT" | "ADMIN_CREATED" | "SSO";
export type BusinessSystemStatus = "ACTIVE" | "DISABLED";
export type SystemRole = "SYSTEM_OWNER";

export interface SystemRoleView {
  system_id: string;
  role: SystemRole;
}

export interface CurrentUser {
  id: string;
  username: string;
  display_name: string;
  role: AccountRole;
  status: AccountStatus;
  must_change_password: boolean;
  system_roles: SystemRoleView[];
}

export interface SessionView {
  user: CurrentUser;
  must_change_password: boolean;
  csrf_token: string;
  expires_at: string;
}

export interface AccountView {
  id: string;
  username: string;
  display_name: string;
  role: AccountRole;
  source: AccountSource;
  status: AccountStatus;
  must_change_password: boolean;
  credential_batch: string | null;
  external_provider: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccountPage {
  items: AccountView[];
  page: number;
  page_size: number;
  total: number;
}

export interface SystemOwnerView {
  account_id: string;
  username: string;
  display_name: string;
}

export interface BusinessSystemView {
  id: string;
  code: string;
  name: string;
  description: string | null;
  status: BusinessSystemStatus;
  owners: SystemOwnerView[];
  created_at: string;
  updated_at: string;
}

export interface BusinessSystemPage {
  items: BusinessSystemView[];
  page: number;
  page_size: number;
  total: number;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id: string;
  details?: Record<string, string | number | boolean> | null;
}
