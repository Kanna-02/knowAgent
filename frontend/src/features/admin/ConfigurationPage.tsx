import {
  App,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
} from "antd";
import { CheckCircle2, Plus, RefreshCw, Settings2 } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { FormInstance } from "antd";

import { apiClient } from "../../api/client";
import type { PromptDefinitionView, PromptScenario, RetrievalProfileView } from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";
import { NotificationSettingsPanel } from "./NotificationSettingsPanel";

interface PromptFormValues {
  scenario: PromptScenario;
  version: string;
  content: string;
  change_note: string;
}

type ProfileFormValues = Omit<RetrievalProfileView, "is_active" | "created_at">;

const DEFAULT_PROFILE: ProfileFormValues = {
  name: "default",
  version: "",
  keyword_top_k: 20,
  vector_top_k: 20,
  result_top_k: 10,
  rrf_k: 60,
  keyword_weight: 1,
  vector_weight: 1,
  rerank_candidate_top_k: 20,
  rerank_top_k: 10,
  evidence_max_items: 6,
  evidence_max_characters: 12000,
  change_note: "",
};

export function ConfigurationPage(): ReactNode {
  const { message } = App.useApp();
  const [promptForm] = Form.useForm<PromptFormValues>();
  const [profileForm] = Form.useForm<ProfileFormValues>();
  const [prompts, setPrompts] = useState<PromptDefinitionView[]>([]);
  const [profiles, setProfiles] = useState<RetrievalProfileView[]>([]);
  const [promptLoading, setPromptLoading] = useState(true);
  const [profileLoading, setProfileLoading] = useState(true);
  const [promptError, setPromptError] = useState<UiError | null>(null);
  const [profileError, setProfileError] = useState<UiError | null>(null);
  const [promptOpen, setPromptOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const promptRequestId = useRef(0);
  const profileRequestId = useRef(0);

  const loadPrompts = useCallback(async (): Promise<void> => {
    const current = ++promptRequestId.current;
    setPromptLoading(true);
    try {
      const result = await apiClient.listPromptDefinitions({ page: 1, pageSize: 100 });
      if (current === promptRequestId.current) {
        setPrompts(result.items);
        setPromptError(null);
      }
    } catch (error: unknown) {
      if (current === promptRequestId.current)
        setPromptError(toUiError(error, "提示词版本加载失败"));
    } finally {
      if (current === promptRequestId.current) setPromptLoading(false);
    }
  }, []);

  const loadProfiles = useCallback(async (): Promise<void> => {
    const current = ++profileRequestId.current;
    setProfileLoading(true);
    try {
      const result = await apiClient.listRetrievalProfiles({ page: 1, pageSize: 100 });
      if (current === profileRequestId.current) {
        setProfiles(result.items);
        setProfileError(null);
      }
    } catch (error: unknown) {
      if (current === profileRequestId.current)
        setProfileError(toUiError(error, "检索配置版本加载失败"));
    } finally {
      if (current === profileRequestId.current) setProfileLoading(false);
    }
  }, []);

  useEffect(() => {
    const promptTimer = window.setTimeout(() => void loadPrompts(), 0);
    const profileTimer = window.setTimeout(() => void loadProfiles(), 0);
    return () => {
      window.clearTimeout(promptTimer);
      window.clearTimeout(profileTimer);
      promptRequestId.current += 1;
      profileRequestId.current += 1;
    };
  }, [loadProfiles, loadPrompts]);

  const savePrompt = async (values: PromptFormValues): Promise<void> => {
    setSaving(true);
    try {
      await apiClient.createPromptDefinition(values);
      void message.success("提示词版本已创建");
      setPromptOpen(false);
      promptForm.resetFields();
      await loadPrompts();
    } catch (error: unknown) {
      void message.error(toUiError(error, "提示词版本创建失败").message);
    } finally {
      setSaving(false);
    }
  };

  const saveProfile = async (values: ProfileFormValues): Promise<void> => {
    setSaving(true);
    try {
      await apiClient.createRetrievalProfile(values);
      void message.success("检索配置版本已创建");
      setProfileOpen(false);
      profileForm.resetFields();
      await loadProfiles();
    } catch (error: unknown) {
      void message.error(toUiError(error, "检索配置版本创建失败").message);
    } finally {
      setSaving(false);
    }
  };

  const activatePrompt = async (item: PromptDefinitionView): Promise<void> => {
    try {
      await apiClient.activatePromptDefinition(item.scenario, item.version);
      void message.success("提示词版本已激活");
      await loadPrompts();
    } catch (error: unknown) {
      void message.error(toUiError(error, "提示词版本激活失败").message);
    }
  };

  const activateProfile = async (item: RetrievalProfileView): Promise<void> => {
    try {
      await apiClient.activateRetrievalProfile(item.name, item.version);
      void message.success("检索配置版本已激活");
      await loadProfiles();
    } catch (error: unknown) {
      void message.error(toUiError(error, "检索配置版本激活失败").message);
    }
  };

  const promptPanel = promptError ? (
    <FeedbackState
      status="error"
      title="提示词版本加载失败"
      error={promptError}
      retryLabel="重试"
      retrying={promptLoading}
      onRetry={() => void loadPrompts()}
    />
  ) : (
    <Table<PromptDefinitionView>
      rowKey={(item) => `${item.scenario}:${item.version}`}
      loading={promptLoading}
      dataSource={prompts}
      pagination={false}
      scroll={{ x: 900 }}
      locale={{ emptyText: "暂无提示词版本" }}
      columns={[
        { title: "场景", dataIndex: "scenario", width: 160, render: promptScenarioLabel },
        { title: "版本", dataIndex: "version", width: 180 },
        {
          title: "状态",
          dataIndex: "enabled",
          width: 100,
          render: (enabled: boolean) =>
            enabled ? <Tag color="success">已激活</Tag> : <Tag>未激活</Tag>,
        },
        { title: "变更说明", dataIndex: "change_note", width: 280, ellipsis: true },
        {
          title: "创建时间",
          dataIndex: "created_at",
          width: 180,
          render: (value: string) => new Date(value).toLocaleString(),
        },
        {
          title: "操作",
          key: "actions",
          width: 110,
          fixed: "right",
          render: (_, item) =>
            item.enabled ? null : (
              <Popconfirm
                title="激活此提示词版本？"
                description="同场景当前版本将立即停用。"
                okText="激活"
                cancelText="取消"
                onConfirm={() => void activatePrompt(item)}
              >
                <Button size="small" icon={<CheckCircle2 size={15} />}>
                  激活
                </Button>
              </Popconfirm>
            ),
        },
      ]}
    />
  );

  const profilePanel = profileError ? (
    <FeedbackState
      status="error"
      title="检索配置版本加载失败"
      error={profileError}
      retryLabel="重试"
      retrying={profileLoading}
      onRetry={() => void loadProfiles()}
    />
  ) : (
    <Table<RetrievalProfileView>
      rowKey={(item) => `${item.name}:${item.version}`}
      loading={profileLoading}
      dataSource={profiles}
      pagination={false}
      scroll={{ x: 1160 }}
      locale={{ emptyText: "暂无检索配置版本" }}
      columns={[
        { title: "配置名", dataIndex: "name", width: 120 },
        { title: "版本", dataIndex: "version", width: 160 },
        {
          title: "状态",
          dataIndex: "is_active",
          width: 100,
          render: (active: boolean) =>
            active ? <Tag color="success">已激活</Tag> : <Tag>未激活</Tag>,
        },
        { title: "关键词 Top-K", dataIndex: "keyword_top_k", width: 130 },
        { title: "向量 Top-K", dataIndex: "vector_top_k", width: 120 },
        { title: "结果 Top-K", dataIndex: "result_top_k", width: 120 },
        { title: "Rerank 候选", dataIndex: "rerank_candidate_top_k", width: 130 },
        { title: "证据条数", dataIndex: "evidence_max_items", width: 110 },
        { title: "变更说明", dataIndex: "change_note", width: 260, ellipsis: true },
        {
          title: "操作",
          key: "actions",
          width: 110,
          fixed: "right",
          render: (_, item) =>
            item.is_active ? null : (
              <Popconfirm
                title="激活此检索配置？"
                description="同名当前版本将立即停用。"
                okText="激活"
                cancelText="取消"
                onConfirm={() => void activateProfile(item)}
              >
                <Button size="small" icon={<CheckCircle2 size={15} />}>
                  激活
                </Button>
              </Popconfirm>
            ),
        },
      ]}
    />
  );

  return (
    <section className="page-section">
      <div className="page-heading-row">
        <div>
          <h1>问答配置</h1>
          <p>提示词、检索版本与通知接口</p>
        </div>
        <Settings2 size={22} aria-hidden="true" />
      </div>
      <Tabs
        items={[
          {
            key: "prompts",
            label: "提示词版本",
            children: (
              <>
                <ConfigurationToolbar
                  summary={`共 ${prompts.length} 个版本`}
                  createLabel="新建提示词版本"
                  loading={promptLoading}
                  onCreate={() => setPromptOpen(true)}
                  onRefresh={() => void loadPrompts()}
                />
                {promptPanel}
              </>
            ),
          },
          {
            key: "profiles",
            label: "检索配置版本",
            children: (
              <>
                <ConfigurationToolbar
                  summary={`共 ${profiles.length} 个版本`}
                  createLabel="新建检索配置版本"
                  loading={profileLoading}
                  onCreate={() => {
                    profileForm.setFieldsValue(DEFAULT_PROFILE);
                    setProfileOpen(true);
                  }}
                  onRefresh={() => void loadProfiles()}
                />
                {profilePanel}
              </>
            ),
          },
          {
            key: "notifications",
            label: "通知接口",
            children: <NotificationSettingsPanel />,
          },
        ]}
      />
      <PromptDrawer
        open={promptOpen}
        saving={saving}
        form={promptForm}
        onClose={() => setPromptOpen(false)}
        onSave={savePrompt}
      />
      <ProfileDrawer
        open={profileOpen}
        saving={saving}
        form={profileForm}
        onClose={() => setProfileOpen(false)}
        onSave={saveProfile}
      />
    </section>
  );
}

function ConfigurationToolbar({
  summary,
  createLabel,
  loading,
  onCreate,
  onRefresh,
}: {
  summary: string;
  createLabel: string;
  loading: boolean;
  onCreate: () => void;
  onRefresh: () => void;
}): ReactNode {
  return (
    <div className="table-toolbar">
      <span className="toolbar-summary">{summary}</span>
      <Space>
        <Tooltip title="刷新">
          <Button
            icon={<RefreshCw size={16} />}
            aria-label={`刷新${createLabel.replace("新建", "")}`}
            loading={loading}
            onClick={onRefresh}
          />
        </Tooltip>
        <Button type="primary" icon={<Plus size={16} />} onClick={onCreate}>
          {createLabel}
        </Button>
      </Space>
    </div>
  );
}

function PromptDrawer({
  open,
  saving,
  form,
  onClose,
  onSave,
}: {
  open: boolean;
  saving: boolean;
  form: FormInstance<PromptFormValues>;
  onClose: () => void;
  onSave: (values: PromptFormValues) => Promise<void>;
}): ReactNode {
  return (
    <Drawer title="新建提示词版本" open={open} size={560} onClose={onClose} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={(values) => void onSave(values)}>
        <Form.Item name="scenario" label="场景" rules={[{ required: true }]}>
          <Select options={PROMPT_SCENARIOS} />
        </Form.Item>
        <Form.Item name="version" label="版本" rules={[{ required: true, max: 100 }]}>
          <Input placeholder="例如 grounded-answer-v2" />
        </Form.Item>
        <Form.Item name="content" label="提示词内容" rules={[{ required: true }]}>
          <Input.TextArea rows={10} maxLength={12000} showCount />
        </Form.Item>
        <Form.Item name="change_note" label="变更说明" rules={[{ required: true, max: 500 }]}>
          <Input.TextArea rows={3} maxLength={500} showCount />
        </Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" loading={saving}>
            创建版本
          </Button>
          <Button onClick={onClose}>取消</Button>
        </Space>
      </Form>
    </Drawer>
  );
}

function ProfileDrawer({
  open,
  saving,
  form,
  onClose,
  onSave,
}: {
  open: boolean;
  saving: boolean;
  form: FormInstance<ProfileFormValues>;
  onClose: () => void;
  onSave: (values: ProfileFormValues) => Promise<void>;
}): ReactNode {
  return (
    <Drawer title="新建检索配置版本" open={open} size={640} onClose={onClose} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={(values) => void onSave(values)}>
        <div className="configuration-form-grid">
          <TextField name="name" label="配置名" />
          <TextField name="version" label="版本" />
          <NumberField name="keyword_top_k" label="关键词 Top-K" form={form} />
          <NumberField name="vector_top_k" label="向量 Top-K" form={form} />
          <NumberField
            name="result_top_k"
            label="结果 Top-K"
            form={form}
            crossFieldValidator={validateRetrievalResultBudget}
          />
          <NumberField name="rrf_k" label="RRF K" />
          <NumberField name="keyword_weight" label="关键词权重" step={0.1} />
          <NumberField name="vector_weight" label="向量权重" step={0.1} />
          <NumberField
            name="rerank_candidate_top_k"
            label="Rerank 候选数"
            form={form}
            crossFieldValidator={validateRerankCandidateBudget}
          />
          <NumberField
            name="rerank_top_k"
            label="Rerank 结果数"
            form={form}
            crossFieldValidator={validateRerankChain}
          />
          <NumberField name="evidence_max_items" label="证据条数上限" />
          <NumberField name="evidence_max_characters" label="证据字符上限" />
        </div>
        <Form.Item name="change_note" label="变更说明" rules={[{ required: true, max: 500 }]}>
          <Input.TextArea rows={3} maxLength={500} showCount />
        </Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" loading={saving}>
            创建版本
          </Button>
          <Button onClick={onClose}>取消</Button>
        </Space>
      </Form>
    </Drawer>
  );
}

type CrossFieldValidator = (
  getFieldValue: (name: keyof ProfileFormValues) => unknown,
  value: number,
) => string | undefined;

const validateRetrievalResultBudget: CrossFieldValidator = (getFieldValue, value) => {
  const keyword = getFieldValue("keyword_top_k");
  const vector = getFieldValue("vector_top_k");
  if (typeof keyword !== "number" || typeof vector !== "number") return undefined;
  if (value > keyword + vector) return "结果 Top-K 不能超过关键词与向量 Top-K 之和";
  return undefined;
};

const validateRerankCandidateBudget: CrossFieldValidator = (getFieldValue, value) => {
  const keyword = getFieldValue("keyword_top_k");
  const vector = getFieldValue("vector_top_k");
  if (typeof keyword !== "number" || typeof vector !== "number") return undefined;
  if (value > keyword + vector) return "Rerank 候选数不能超过关键词与向量 Top-K 之和";
  return undefined;
};

const validateRerankChain: CrossFieldValidator = (getFieldValue, value) => {
  const resultTopK = getFieldValue("result_top_k");
  const rerankCandidate = getFieldValue("rerank_candidate_top_k");
  if (typeof rerankCandidate !== "number") return undefined;
  if (typeof resultTopK !== "number") return undefined;
  if (!(value >= resultTopK && value <= rerankCandidate))
    return "Rerank 结果数需满足：结果 Top-K ≤ Rerank 结果数 ≤ Rerank 候选数";
  return undefined;
};

function TextField({ name, label }: { name: keyof ProfileFormValues; label: string }): ReactNode {
  return (
    <Form.Item name={name} label={label} rules={[{ required: true, max: 100 }]}>
      <Input />
    </Form.Item>
  );
}

function NumberField({
  name,
  label,
  step = 1,
  form,
  crossFieldValidator,
}: {
  name: keyof ProfileFormValues;
  label: string;
  step?: number;
  form?: FormInstance<ProfileFormValues>;
  crossFieldValidator?: CrossFieldValidator;
}): ReactNode {
  return (
    <Form.Item
      name={name}
      label={label}
      rules={[
        { required: true },
        {
          validator: (_rule, value) => {
            if (!crossFieldValidator || !form || value == null) return Promise.resolve();
            const message = crossFieldValidator(
              (field) => form.getFieldValue(field),
              value as number,
            );
            return message ? Promise.reject(new Error(message)) : Promise.resolve();
          },
        },
      ]}
    >
      <InputNumber min={step} step={step} precision={step < 1 ? 2 : 0} />
    </Form.Item>
  );
}

const PROMPT_SCENARIOS: { value: PromptScenario; label: string }[] = [
  { value: "grounded_answer", label: "证据回答" },
  { value: "query_rewrite", label: "查询改写" },
];

function promptScenarioLabel(scenario: PromptScenario): string {
  return PROMPT_SCENARIOS.find((item) => item.value === scenario)?.label ?? scenario;
}
