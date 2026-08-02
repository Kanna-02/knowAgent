import { App, Button, Form, Input } from "antd";
import { Check, KeyRound, LogOut, ShieldCheck } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { passwordViolations, resolvePostLoginPath } from "./authPolicy";
import { useAuth } from "./authContextValue";

interface PasswordValues {
  currentPassword: string;
  newPassword: string;
  confirmation: string;
}

export function ChangePasswordPage(): ReactNode {
  const { message } = App.useApp();
  const { user, loading, changePassword, logout } = useAuth();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  if (loading) return <div className="center-state" />;
  if (!user) return <Navigate replace to="/login" />;

  const submit = async (values: PasswordValues): Promise<void> => {
    setSubmitting(true);
    try {
      const current = await changePassword(values.currentPassword, values.newPassword);
      void message.success("密码已更新");
      void navigate(resolvePostLoginPath(current.role, false), { replace: true });
    } catch (error: unknown) {
      void message.error(error instanceof ApiError ? error.message : "密码更新失败，请重试");
    } finally {
      setSubmitting(false);
    }
  };

  const signOut = async (): Promise<void> => {
    try {
      await logout();
    } finally {
      void navigate(user.role === "ADMIN" ? "/admin/login" : "/login", { replace: true });
    }
  };

  return (
    <main className="password-screen">
      <section className="password-panel">
        <div className="brand-mark password-mark">
          <ShieldCheck size={22} aria-hidden="true" />
        </div>
        <div className="auth-heading">
          <span className="auth-entry-label">账号安全</span>
          <h1>首次登录，请修改密码</h1>
          <p>{user.display_name}</p>
        </div>
        <Form<PasswordValues>
          layout="vertical"
          requiredMark={false}
          size="large"
          onFinish={(values) => void submit(values)}
        >
          <Form.Item
            name="currentPassword"
            label="当前密码"
            rules={[{ required: true, message: "请输入当前密码" }]}
          >
            <Input.Password autoComplete="current-password" prefix={<KeyRound size={17} />} />
          </Form.Item>
          <Form.Item
            name="newPassword"
            label="新密码"
            rules={[
              { required: true, message: "请输入新密码" },
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
            <Input.Password autoComplete="new-password" prefix={<KeyRound size={17} />} />
          </Form.Item>
          <Form.Item
            name="confirmation"
            label="确认新密码"
            dependencies={["newPassword"]}
            rules={[
              { required: true, message: "请再次输入新密码" },
              ({ getFieldValue }) => ({
                validator: (_, value: string | undefined) => {
                  if (value && value !== getFieldValue("newPassword")) {
                    return Promise.reject(new Error("两次输入的密码不一致"));
                  }
                  return Promise.resolve();
                },
              }),
            ]}
          >
            <Input.Password autoComplete="new-password" prefix={<Check size={17} />} />
          </Form.Item>
          <Button block type="primary" htmlType="submit" loading={submitting}>
            更新密码
          </Button>
          <Button block type="text" icon={<LogOut size={16} />} onClick={() => void signOut()}>
            退出登录
          </Button>
        </Form>
      </section>
    </main>
  );
}
