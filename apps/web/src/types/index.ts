export type LoginResponse = {
  access_token: string;
  token_type: string;
};

export type User = {
  id: number;
  username: string;
  full_name: string;
  role: "admin" | "business";
};

export type Chart = {
  id: number;
  title: string;
  chart_type: string;
  chart_spec: Record<string, unknown> & { rows?: Record<string, unknown>[] };
};

export type Dashboard = {
  id: number;
  name: string;
};

export type StagingTableMeta = {
  sheet_name: string;
  table: string;
  schema: string | null;
  qualified: string;
  row_count: number;
  columns: { name: string; dtype: string }[];
};

export type DataSource = {
  id: number;
  name: string;
  source_type: string;
  status: string;
  connection_info?: {
    filename?: string;
    sheets?: { sheet_name: string; table_slug?: string; row_count?: number }[];
    staging?: { dialect?: string; tables?: StagingTableMeta[] };
    error?: string;
  };
};

export type ThemeLibrary = {
  id: number;
  name: string;
  description: string;
  status: string;
  data_source_id?: number | null;
};
