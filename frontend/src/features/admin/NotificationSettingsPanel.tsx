import { App, Button, Form, Input, InputNumber, Select, Space, Switch, Tooltip } from "antd";
import { RefreshCw, Save } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type {
  NotificationAuthType,
  NotificationConfigurationUpdate,
  NotificationConfigurationView,
} from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";

interface NotificationFormValues {
  enabled: boolean;
  endpoint_url: string;
  auth_type: NotificationAuthType;
  auth_header_name: string | null;
  secret_reference: string | null;
  ticket_created_template: string;
  ticket_replied_template: string;
  success_status_codes: string;
  timeout_seconds: number;
  max_attempts: number;
  retry_base_seconds: number;
}

export function NotificationSettingsPanel(): ReactNode {
  const { message } = App.useApp();
  const [form] = Form.useForm<NotificationFormValues>();
  const enabled = Form.useWatch("enabled", form);
  const authType = Form.useWatch("auth_type", form);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<UiError | null>(null);
  const requestId = useRef(0);

  const load = useCallback(async (): Promise<void> => {
    const current = ++requestId.current;
    setLoading(true);
    try {
      const configuration = await apiClient.getNotificationConfiguration();
      if (current === requestId.current) {
        form.setFieldsValue(toFormValues(configuration));
        setLoadError(null);
      }
    } catch (error: unknown) {
      if (current === requestId.current) setLoadError(toUiError(error, "通知配置加载失败"));
    } finally {
      if (current === requestId.current) setLoading(false);
    }
  }, [form]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => {
      window.clearTimeout(timer);
      requestId.current += 1;
    };
  }, [load]);

  const save = async (values: NotificationFormValues): Promise<void> => {
    setSaving(true);
    try {
      const saved = await apiClient.updateNotificationConfiguration(toUpdate(values));
      form.setFieldsValue(toFormValues(saved));
      void message.success("通知配置已保存");
    } catch (error: unknown) {
      void message.error(toUiError(error, "通知配置保存失败").message);
    } finally {
      setSaving(false);
    }
  };

  if (loadError) {
    return (
      <FeedbackState
        status="error"
        title="通知配置加载失败"
        error={loadError}
        retryLabel="重试加载通知配置"
        retrying={loading}
        onRetry={() => void load()}
      />
    );
  }

  return (
    <div className="notification-configuration">
      <div className="table-toolbar">
        <span className="toolbar-summary">最后保存后由通知 Worker 自动应用</span>
        <Tooltip title="刷新">
          <Button
            icon={<RefreshCw size={16} />}
            aria-label="刷新通知配置"
            loading={loading}
            onClick={() => void load()}
          />
        </Tooltip>
      </div>
      <Form
        form={form}
        layout="vertical"
        className="notification-configuration-form"
        disabled={loading}
        onFinish={(values) => void save(values)}
      >
        <div className="notification-form-grid">
          <Form.Item name="enabled" label="启用通知" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            name="endpoint_url"
            label="通知地址"
            rules={[{ required: enabled, type: "url", max: 2048 }]}
          >
            <Input placeholder="https://notify.company.internal/api/messages" />
          </Form.Item>
          <Form.Item name="auth_type" label="鉴权方式" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "NONE", label: "无鉴权" },
                { value: "BEARER", label: "Bearer Token" },
                { value: "HEADER", label: "自定义 Header" },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="auth_header_name"
            label="鉴权 Header"
            rules={[{ required: authType !== "NONE", max: 128 }]}
          >
            <Input disabled={authType === "NONE"} placeholder="Authorization" />
          </Form.Item>
          <Form.Item
            name="secret_reference"
            label="密钥引用"
            extra="密钥值不会保存到数据库，仅在 Worker 运行环境中解析。"
            rules={[{ required: authType !== "NONE", max: 128 }]}
          >
            <Input disabled={authType === "NONE"} placeholder="KNOWAGENT_NOTIFICATION_TOKEN" />
          </Form.Item>
          <Form.Item
            name="success_status_codes"
            label="成功状态码"
            rules={[
              { required: true },
              { pattern: /^2\d\d(?:\s*,\s*2\d\d)*$/, message: "请输入逗号分隔的 2xx 状态码" },
            ]}
          >
            <Input placeholder="200, 201, 202, 204" />
          </Form.Item>
          <Form.Item name="timeout_seconds" label="超时（秒）" rules={[{ required: true }]}>
            <InputNumber min={1} max={120} />
          </Form.Item>
          <Form.Item name="max_attempts" label="每周期最大尝试" rules={[{ required: true }]}>
            <InputNumber min={1} max={10} />
          </Form.Item>
          <Form.Item
            name="retry_base_seconds"
            label="重试退避基数（秒）"
            rules={[{ required: true }]}
          >
            <InputNumber min={1} max={86400} />
          </Form.Item>
        </div>
        <Form.Item name="ticket_created_template" label="工单创建模板" rules={[{ required: true }]}>
          <Input.TextArea rows={6} maxLength={32768} showCount />
        </Form.Item>
        <Form.Item
          name="ticket_replied_template"
          label="负责人回复模板"
          rules={[{ required: true }]}
        >
          <Input.TextArea rows={6} maxLength={32768} showCount />
        </Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" icon={<Save size={16} />} loading={saving}>
            保存通知配置
          </Button>
        </Space>
      </Form>
    </div>
  );
}

function toFormValues(configuration: NotificationConfigurationView): NotificationFormValues {
  return {
    enabled: configuration.enabled,
    endpoint_url: configuration.endpoint_url,
    auth_type: configuration.auth_type,
    auth_header_name: configuration.auth_header_name,
    secret_reference: configuration.secret_reference,
    ticket_created_template: configuration.ticket_created_template,
    ticket_replied_template: configuration.ticket_replied_template,
    success_status_codes: configuration.success_status_codes.join(", "),
    timeout_seconds: configuration.timeout_seconds,
    max_attempts: configuration.max_attempts,
    retry_base_seconds: configuration.retry_base_seconds,
  };
}

function toUpdate(values: NotificationFormValues): NotificationConfigurationUpdate {
  return {
    ...values,
    auth_header_name: values.auth_type === "NONE" ? null : values.auth_header_name,
    secret_reference: values.auth_type === "NONE" ? null : values.secret_reference,
    success_status_codes: values.success_status_codes
      .split(",")
      .map((value) => Number(value.trim())),
  };
}
