import {
  Alert,
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
import { Pencil, Plus, Power, RefreshCw, ServerCog, UserRoundCog } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { AccountView, BusinessSystemStatus, BusinessSystemView } from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";

interface SystemFormValues {
  code: string;
  name: string;
  description?: string;
}

export function SystemsPage(): ReactNode {
  const { message } = App.useApp();
  const [form] = Form.useForm<SystemFormValues>();
  const [systems, setSystems] = useState<BusinessSystemView[]>([]);
  const [ownerAccounts, setOwnerAccounts] = useState<AccountView[]>([]);
  const [systemsLoading, setSystemsLoading] = useState(true);
  const [systemsError, setSystemsError] = useState<UiError | null>(null);
  const [ownersLoading, setOwnersLoading] = useState(true);
  const [ownerError, setOwnerError] = useState<string | null>(null);
  const [ownerSearch, setOwnerSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [saving, setSaving] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingSystem, setEditingSystem] = useState<BusinessSystemView | null>(null);
  const [ownerSystem, setOwnerSystem] = useState<BusinessSystemView | null>(null);
  const [ownerIds, setOwnerIds] = useState<string[]>([]);
  const systemsRequestId = useRef(0);
  const ownerRequestId = useRef(0);

  const loadSystems = useCallback(
    async (targetPage = page, targetPageSize = pageSize): Promise<void> => {
      const requestId = ++systemsRequestId.current;
      setSystemsLoading(true);
      try {
        const result = await apiClient.listAdminSystems({
          page: targetPage,
          pageSize: targetPageSize,
        });
        if (requestId === systemsRequestId.current) {
          setSystems(result.items);
          setTotal(result.total);
          setSystemsError(null);
        }
      } catch (error: unknown) {
        if (requestId === systemsRequestId.current) {
          setSystemsError(toUiError(error, "业务系统列表加载失败"));
        }
      } finally {
        if (requestId === systemsRequestId.current) setSystemsLoading(false);
      }
    },
    [page, pageSize],
  );

  const loadOwnerAccounts = useCallback(async (search = ""): Promise<void> => {
    const requestId = ++ownerRequestId.current;
    setOwnerSearch(search);
    setOwnersLoading(true);
    try {
      const accounts = await apiClient.listAccounts({
        page: 1,
        pageSize: 100,
        role: "SYSTEM_OWNER",
        status: "ACTIVE",
        ...(search.trim() ? { search: search.trim() } : {}),
      });
      if (requestId !== ownerRequestId.current) return;
      setOwnerAccounts(accounts.items);
      setOwnerError(null);
    } catch (error: unknown) {
      if (requestId !== ownerRequestId.current) return;
      setOwnerError(toUiError(error, "负责人候选加载失败").message);
    } finally {
      if (requestId === ownerRequestId.current) setOwnersLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadSystems(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      systemsRequestId.current += 1;
    };
  }, [loadSystems]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadOwnerAccounts(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      ownerRequestId.current += 1;
    };
  }, [loadOwnerAccounts]);

  const openCreate = (): void => {
    setEditingSystem(null);
    form.resetFields();
    setEditorOpen(true);
  };

  const openEdit = (businessSystem: BusinessSystemView): void => {
    setEditingSystem(businessSystem);
    form.resetFields();
    form.setFieldsValue({
      code: businessSystem.code,
      name: businessSystem.name,
      description: businessSystem.description ?? "",
    });
    setEditorOpen(true);
  };

  const saveSystem = async (values: SystemFormValues): Promise<void> => {
    setSaving(true);
    try {
      if (editingSystem) {
        await apiClient.updateSystem(editingSystem.id, {
          name: values.name,
          description: values.description?.trim() || null,
        });
        void message.success("业务系统已更新");
      } else {
        await apiClient.createSystem({
          code: values.code,
          name: values.name,
          description: values.description?.trim() || null,
        });
        void message.success("业务系统已创建");
      }
      setEditorOpen(false);
      form.resetFields();
      if (editingSystem) {
        await loadSystems();
      } else {
        setPage(1);
        await loadSystems(1, pageSize);
      }
    } catch (error: unknown) {
      void message.error(toUiError(error, "业务系统保存失败").message);
    } finally {
      setSaving(false);
    }
  };

  const changeStatus = async (businessSystem: BusinessSystemView): Promise<void> => {
    const nextStatus: BusinessSystemStatus =
      businessSystem.status === "ACTIVE" ? "DISABLED" : "ACTIVE";
    try {
      await apiClient.updateSystem(businessSystem.id, { status: nextStatus });
      void message.success(nextStatus === "ACTIVE" ? "业务系统已启用" : "业务系统已停用");
      await loadSystems();
    } catch (error: unknown) {
      void message.error(toUiError(error, "业务系统状态更新失败").message);
    }
  };

  const openOwners = (businessSystem: BusinessSystemView): void => {
    setOwnerSystem(businessSystem);
    setOwnerIds(businessSystem.owners.map((owner) => owner.account_id));
  };

  const saveOwners = async (): Promise<void> => {
    if (!ownerSystem) return;
    setSaving(true);
    try {
      await apiClient.assignSystemOwners(ownerSystem.id, ownerIds, true);
      void message.success("系统负责人已更新");
      setOwnerSystem(null);
      await loadSystems();
    } catch (error: unknown) {
      void message.error(toUiError(error, "负责人配置失败").message);
    } finally {
      setSaving(false);
    }
  };

  const ownerOptions = new Map<string, string>();
  for (const owner of ownerSystem?.owners ?? []) {
    ownerOptions.set(owner.account_id, `${owner.display_name} (${owner.username})`);
  }
  for (const account of ownerAccounts) {
    ownerOptions.set(account.id, `${account.display_name} (${account.username})`);
  }

  return (
    <section className="page-section">
      <div className="page-heading-row">
        <div>
          <h1>业务系统</h1>
          <p>共 {total} 个系统</p>
        </div>
        <Button
          type="primary"
          icon={<Plus size={17} />}
          aria-label="新增业务系统"
          onClick={openCreate}
        >
          新增系统
        </Button>
      </div>
      <div className="table-toolbar">
        <span className="toolbar-summary">系统标识创建后不可修改</span>
        <Tooltip title="刷新">
          <Button
            icon={<RefreshCw size={16} />}
            aria-label="刷新业务系统列表"
            onClick={() => {
              void loadSystems();
              void loadOwnerAccounts(ownerSearch);
            }}
          />
        </Tooltip>
      </div>
      {systemsError ? (
        <FeedbackState
          status="error"
          title="业务系统列表加载失败"
          error={systemsError}
          retryLabel="重试加载业务系统列表"
          retrying={systemsLoading}
          onRetry={() => void loadSystems()}
        />
      ) : null}
      <Table<BusinessSystemView>
        rowKey="id"
        loading={systemsLoading}
        dataSource={systems}
        scroll={{ x: 880 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: (nextPage, nextPageSize) => {
            setPage(nextPage);
            setPageSize(nextPageSize);
          },
        }}
        locale={{ emptyText: "暂无业务系统" }}
        columns={[
          {
            title: "系统",
            dataIndex: "name",
            width: 260,
            render: (value: string, item) => (
              <div className="account-cell">
                <strong>{value}</strong>
                <span>{item.code}</span>
              </div>
            ),
          },
          {
            title: "说明",
            dataIndex: "description",
            ellipsis: true,
            render: (value: string | null) => value || "-",
          },
          {
            title: "负责人",
            dataIndex: "owners",
            width: 220,
            render: (owners: BusinessSystemView["owners"]) =>
              owners.length ? owners.map((owner) => owner.display_name).join("、") : "未配置",
          },
          {
            title: "状态",
            dataIndex: "status",
            width: 110,
            render: (value: BusinessSystemStatus) =>
              value === "ACTIVE" ? <Tag color="success">已启用</Tag> : <Tag>已停用</Tag>,
          },
          {
            title: "操作",
            key: "actions",
            width: 150,
            fixed: "right",
            render: (_, item) => (
              <Space size={0}>
                <Tooltip title="编辑">
                  <Button
                    type="text"
                    icon={<Pencil size={16} />}
                    aria-label="编辑业务系统"
                    onClick={() => openEdit(item)}
                  />
                </Tooltip>
                <Tooltip title="配置负责人">
                  <Button
                    type="text"
                    icon={<UserRoundCog size={16} />}
                    aria-label="配置系统负责人"
                    onClick={() => openOwners(item)}
                  />
                </Tooltip>
                <Popconfirm
                  title={item.status === "ACTIVE" ? "停用此系统？" : "启用此系统？"}
                  description={
                    item.status === "ACTIVE" ? "停用后普通用户不能再选择此系统。" : undefined
                  }
                  okText="确认"
                  cancelText="取消"
                  onConfirm={() => void changeStatus(item)}
                >
                  <Tooltip title={item.status === "ACTIVE" ? "停用" : "启用"}>
                    <Button type="text" icon={<Power size={16} />} aria-label="切换系统状态" />
                  </Tooltip>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Drawer
        title={
          <span className="drawer-title">
            <ServerCog size={18} /> {editingSystem ? "编辑业务系统" : "新增业务系统"}
          </span>
        }
        size={440}
        open={editorOpen}
        destroyOnHidden
        onClose={() => setEditorOpen(false)}
        extra={
          <Button
            type="primary"
            aria-label={editingSystem ? "保存业务系统" : "创建业务系统"}
            loading={saving}
            onClick={() => form.submit()}
          >
            {editingSystem ? "保存" : "创建"}
          </Button>
        }
      >
        <Form<SystemFormValues>
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => void saveSystem(values)}
        >
          <Form.Item
            name="code"
            label="系统标识"
            rules={[
              { required: true, message: "请输入系统标识" },
              {
                pattern: /^[A-Za-z][A-Za-z0-9_-]{1,31}$/,
                message: "请输入 2-32 位字母、数字、下划线或连字符",
              },
            ]}
          >
            <Input disabled={Boolean(editingSystem)} autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="name"
            label="系统名称"
            rules={[{ required: true, whitespace: true, message: "请输入系统名称" }]}
          >
            <Input autoComplete="off" maxLength={100} />
          </Form.Item>
          <Form.Item name="description" label="系统说明">
            <Input.TextArea rows={4} maxLength={500} showCount />
          </Form.Item>
        </Form>
      </Drawer>
      <Drawer
        title={
          <span className="drawer-title">
            <UserRoundCog size={18} /> 配置负责人
          </span>
        }
        size={440}
        open={Boolean(ownerSystem)}
        destroyOnHidden
        onClose={() => setOwnerSystem(null)}
        extra={
          <Button
            type="primary"
            aria-label="保存系统负责人"
            loading={saving}
            onClick={() => void saveOwners()}
          >
            保存
          </Button>
        }
      >
        <p className="drawer-context">{ownerSystem?.name}</p>
        {ownerError ? (
          <Alert
            type="error"
            showIcon
            message={ownerError}
            action={
              <Button
                size="small"
                aria-label="重试加载负责人候选"
                onClick={() => void loadOwnerAccounts(ownerSearch)}
              >
                重试
              </Button>
            }
          />
        ) : null}
        {!ownersLoading &&
        !ownerError &&
        ownerAccounts.length === 0 &&
        (ownerSystem?.owners.length ?? 0) === 0 ? (
          <Alert
            type="info"
            showIcon
            message="暂无可选的系统负责人账号"
            description="请先在用户与角色中新增系统负责人。"
            action={
              <Button type="link" href="/admin/accounts">
                新增负责人
              </Button>
            }
          />
        ) : null}
        <Select<string[]>
          mode="multiple"
          value={ownerIds}
          loading={ownersLoading}
          showSearch
          filterOption={false}
          placeholder="选择系统负责人"
          aria-label="系统负责人"
          className="full-width-control"
          options={[...ownerOptions].map(([value, label]) => ({ value, label }))}
          onSearch={(value) => void loadOwnerAccounts(value)}
          onChange={setOwnerIds}
        />
      </Drawer>
    </section>
  );
}
