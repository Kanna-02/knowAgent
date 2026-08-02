import {
  App,
  Button,
  Drawer,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
} from "antd";
import type { TablePaginationConfig } from "antd/es/table";
import { Plus, Power, RefreshCw, ShieldCheck, UserRoundPlus } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { AccountRole, AccountStatus, AccountView } from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";
import { passwordViolations } from "../auth/authPolicy";

interface AdminFormValues {
  username: string;
  displayName: string;
  temporaryPassword: string;
}

const roleLabels: Record<AccountRole, string> = {
  USER: "普通用户",
  SYSTEM_OWNER: "系统负责人",
  ADMIN: "平台管理员",
};

const sourceLabels = {
  LOCAL_IMPORT: "批量导入",
  ADMIN_CREATED: "后台新增",
  SSO: "SSO",
} as const;

export function AccountsPage(): ReactNode {
  const { message } = App.useApp();
  const [form] = Form.useForm<AdminFormValues>();
  const [items, setItems] = useState<AccountView[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [role, setRole] = useState<AccountRole | null>(null);
  const [status, setStatus] = useState<AccountStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<UiError | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const loadRequestId = useRef(0);

  const load = useCallback(async (): Promise<void> => {
    const requestId = ++loadRequestId.current;
    setLoading(true);
    try {
      const result = await apiClient.listAccounts({
        page,
        pageSize,
        ...(role ? { role } : {}),
        ...(status ? { status } : {}),
      });
      if (requestId === loadRequestId.current) {
        setItems(result.items);
        setTotal(result.total);
        setLoadError(null);
      }
    } catch (error: unknown) {
      if (requestId === loadRequestId.current) {
        setLoadError(toUiError(error, "账号列表加载失败"));
      }
    } finally {
      if (requestId === loadRequestId.current) setLoading(false);
    }
  }, [page, pageSize, role, status]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      loadRequestId.current += 1;
    };
  }, [load]);

  const createAdmin = async (values: AdminFormValues): Promise<void> => {
    setSaving(true);
    try {
      await apiClient.createAdmin({
        username: values.username,
        display_name: values.displayName,
        temporary_password: values.temporaryPassword,
      });
      void message.success("管理员已新增");
      setDrawerOpen(false);
      form.resetFields();
      await load();
    } catch (error: unknown) {
      void message.error(toUiError(error, "新增管理员失败").message);
    } finally {
      setSaving(false);
    }
  };

  const changeStatus = async (account: AccountView): Promise<void> => {
    const nextStatus: AccountStatus = account.status === "ACTIVE" ? "DISABLED" : "ACTIVE";
    try {
      await apiClient.setAccountStatus(account.id, nextStatus);
      void message.success(nextStatus === "ACTIVE" ? "账号已启用" : "账号已禁用");
      await load();
    } catch (error: unknown) {
      void message.error(toUiError(error, "账号状态更新失败").message);
    }
  };

  return (
    <section className="page-section">
      <div className="page-heading-row">
        <div>
          <h1>用户与角色</h1>
          <p>共 {total} 个账号</p>
        </div>
        <Button
          type="primary"
          icon={<UserRoundPlus size={17} />}
          onClick={() => setDrawerOpen(true)}
        >
          新增管理员
        </Button>
      </div>
      <div className="table-toolbar">
        <Space wrap>
          <Select<AccountRole>
            allowClear
            placeholder="全部角色"
            value={role}
            options={Object.entries(roleLabels).map(([value, label]) => ({
              value: value as AccountRole,
              label,
            }))}
            onChange={(value) => {
              setRole(value);
              setPage(1);
            }}
          />
          <Select<AccountStatus>
            allowClear
            placeholder="全部状态"
            value={status}
            options={[
              { value: "ACTIVE", label: "已启用" },
              { value: "DISABLED", label: "已禁用" },
            ]}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
          />
        </Space>
        <Tooltip title="刷新">
          <Button
            icon={<RefreshCw size={16} />}
            aria-label="刷新账号列表"
            onClick={() => void load()}
          />
        </Tooltip>
      </div>
      {loadError ? (
        <FeedbackState
          status="error"
          title="账号列表加载失败"
          error={loadError}
          retryLabel="重试加载账号列表"
          retrying={loading}
          onRetry={() => void load()}
        />
      ) : null}
      <Table<AccountView>
        rowKey="id"
        loading={loading}
        dataSource={items}
        locale={{ emptyText: "暂无账号" }}
        scroll={{ x: 920 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (value) => `共 ${value} 项`,
        }}
        onChange={(pagination: TablePaginationConfig) => {
          setPage(pagination.current ?? 1);
          setPageSize(pagination.pageSize ?? 20);
        }}
        columns={[
          {
            title: "账号",
            dataIndex: "username",
            width: 180,
            render: (value: string, account) => (
              <div className="account-cell">
                <strong>{value}</strong>
                <span>{account.display_name}</span>
              </div>
            ),
          },
          {
            title: "角色",
            dataIndex: "role",
            width: 140,
            render: (value: AccountRole) => roleLabels[value],
          },
          {
            title: "来源",
            dataIndex: "source",
            width: 120,
            render: (value: AccountView["source"]) => sourceLabels[value],
          },
          {
            title: "首次改密",
            dataIndex: "must_change_password",
            width: 120,
            render: (value: boolean) =>
              value ? <Tag color="warning">待完成</Tag> : <Tag color="success">已完成</Tag>,
          },
          {
            title: "状态",
            dataIndex: "status",
            width: 110,
            render: (value: AccountStatus) =>
              value === "ACTIVE" ? <Tag color="success">已启用</Tag> : <Tag>已禁用</Tag>,
          },
          {
            title: "操作",
            key: "actions",
            width: 96,
            fixed: "right",
            render: (_, account) => (
              <Popconfirm
                title={account.status === "ACTIVE" ? "禁用此账号？" : "启用此账号？"}
                description={
                  account.status === "ACTIVE" ? "该账号的现有会话会立即失效。" : undefined
                }
                okText="确认"
                cancelText="取消"
                onConfirm={() => void changeStatus(account)}
              >
                <Tooltip title={account.status === "ACTIVE" ? "禁用" : "启用"}>
                  <Button type="text" icon={<Power size={16} />} aria-label="切换账号状态" />
                </Tooltip>
              </Popconfirm>
            ),
          },
        ]}
      />
      <Drawer
        title={
          <span className="drawer-title">
            <ShieldCheck size={18} /> 新增管理员
          </span>
        }
        size={440}
        open={drawerOpen}
        destroyOnHidden
        onClose={() => setDrawerOpen(false)}
        extra={
          <Button
            type="text"
            icon={<Plus size={16} />}
            onClick={() => form.submit()}
            loading={saving}
          >
            创建
          </Button>
        }
      >
        <Form<AdminFormValues>
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => void createAdmin(values)}
        >
          <Form.Item
            name="username"
            label="账号"
            rules={[
              { required: true, message: "请输入账号" },
              { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/, message: "账号格式不正确" },
            ]}
          >
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="displayName"
            label="显示名称"
            rules={[{ required: true, whitespace: true, message: "请输入显示名称" }]}
          >
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="temporaryPassword"
            label="临时密码"
            rules={[
              { required: true, message: "请输入临时密码" },
              {
                validator: (_, value: string | undefined) => {
                  if (!value) return Promise.resolve();
                  const violations = passwordViolations(value);
                  return violations.length
                    ? Promise.reject(new Error(violations.join("、")))
                    : Promise.resolve();
                },
              },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Drawer>
    </section>
  );
}
