import { App, Button, Form, Input, Result, Spin } from "antd";
import { ArrowRight, KeyRound, LockKeyhole, RefreshCw, ShieldCheck, UserRound } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { resolvePostLoginPath } from "./authPolicy";
import { useAuth } from "./authContextValue";

interface LoginValues {
  username: string;
  password: string;
}

export function LoginPage({ entry }: { entry: "user" | "admin" }): ReactNode {
  const { message } = App.useApp();
  const { user, loading, bootstrapError, login } = useAuth();
  const navigate = useNavigate();
  const [form] = Form.useForm<LoginValues>();
  const [submitting, setSubmitting] = useState(false);

  if (loading) {
    return (
      <div className="center-state" aria-label="正在检查登录状态">
        <Spin size="large" />
      </div>
    );
  }
  if (bootstrapError) {
    return (
      <Result
        status="error"
        title="无法检查登录状态"
        subTitle={bootstrapError}
        extra={
          <Button icon={<RefreshCw size={16} />} onClick={() => window.location.reload()}>
            重试
          </Button>
        }
      />
    );
  }
  if (user)
    return <Navigate replace to={resolvePostLoginPath(user.role, user.must_change_password)} />;

  const isAdmin = entry === "admin";
  const submit = async (values: LoginValues): Promise<void> => {
    setSubmitting(true);
    try {
      const current = await login(entry, values.username, values.password);
      void navigate(resolvePostLoginPath(current.role, current.must_change_password), {
        replace: true,
      });
    } catch (error: unknown) {
      const text = error instanceof ApiError ? error.message : "登录失败，请稍后重试";
      void message.error(text);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className={`auth-screen ${isAdmin ? "auth-screen-admin" : ""}`}>
      <section className="auth-brand" aria-label="KnowAgent">
        <div className="brand-mark">
          <ShieldCheck size={22} aria-hidden="true" />
        </div>
        <div>
          <div className="brand-name">KnowAgent</div>
          <div className="brand-subtitle">企业知识服务</div>
        </div>
        <div className="auth-brand-footer">
          <KeyRound size={18} aria-hidden="true" />
          <span>{isAdmin ? "平台治理入口" : "内部用户入口"}</span>
        </div>
      </section>
      <section className="auth-form-region">
        <div className="auth-form-wrap">
          <div className="auth-heading">
            <span className="auth-entry-label">{isAdmin ? "管理端" : "用户端"}</span>
            <h1>{isAdmin ? "管理后台登录" : "登录 KnowAgent"}</h1>
          </div>
          <Form
            form={form}
            layout="vertical"
            requiredMark={false}
            size="large"
            onFinish={(values) => void submit(values)}
          >
            <Form.Item
              name="username"
              label="账号"
              rules={[{ required: true, message: "请输入账号" }]}
            >
              <Input
                autoComplete="username"
                prefix={<UserRound size={17} aria-hidden="true" />}
                placeholder="请输入账号"
              />
            </Form.Item>
            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, message: "请输入密码" }]}
            >
              <Input.Password
                autoComplete="current-password"
                prefix={<LockKeyhole size={17} aria-hidden="true" />}
                placeholder="请输入密码"
              />
            </Form.Item>
            <Form.Item className="auth-submit-row">
              <Button
                block
                type="primary"
                htmlType="submit"
                loading={submitting}
                icon={<ArrowRight size={17} aria-hidden="true" />}
                iconPlacement="end"
              >
                登录
              </Button>
            </Form.Item>
          </Form>
        </div>
      </section>
    </main>
  );
}
