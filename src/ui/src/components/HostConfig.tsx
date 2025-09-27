import { Modal, Input, Form, Alert, Button, Space } from "antd";
import { useState } from "react";
import { updateApiUrl } from "@/hooks/useHealthCheck";
import { client } from "@/client/client.gen";
import { healthCheckApiHealthGet } from "@/client/sdk.gen";

interface HostConfigProps {
	visible: boolean;
	currentUrl: string;
	error: string | null;
}

export function HostConfig({ visible, currentUrl, error }: HostConfigProps) {
	const [form] = Form.useForm();
	const [testing, setTesting] = useState(false);
	const [testResult, setTestResult] = useState<{
		success: boolean;
		message: string;
	} | null>(null);

	const testConnection = async (url: string, token: string) => {
		setTesting(true);
		setTestResult(null);

		try {
			// Temporarily set the base URL and token for testing
			const originalConfig = client.getConfig();
			client.setConfig({
				baseUrl: url,
				headers: {
					...originalConfig.headers,
					Authorization: `Bearer ${token}`,
				},
			});

			const { data, response } = await healthCheckApiHealthGet();

			// Check if the response is successful
			if (response.status >= 400) {
				throw new Error(`HTTP ${response.status}: Authentication failed`);
			}

			setTestResult({
				success: true,
				message: `Connected to ${data?.backend || "CTF Proxy"} v${data?.version || "unknown"}`,
			});

			// Restore original config
			client.setConfig(originalConfig);
		} catch (err) {
			setTestResult({
				success: false,
				message:
					err instanceof Error ? err.message : "Failed to connect to server",
			});
		} finally {
			setTesting(false);
		}
	};

	const handleSubmit = async () => {
		try {
			const values = await form.validateFields();
			const url = values.url.replace(/\/$/, ""); // Remove trailing slash
			const token = values.token;

			// Store token in localStorage
			localStorage.setItem("apiToken", token);

			updateApiUrl(url);
		} catch (err) {
			// Validation failed
		}
	};

	return (
		<Modal
			title="Configure API Host"
			open={visible}
			closable={false}
			footer={null}
			width={500}
		>
			<Space direction="vertical" style={{ width: "100%" }} size="large">
				<Alert
					message="Connection Failed"
					description={
						error
							? `Cannot connect to the API server at ${currentUrl}. Error: ${error}`
							: "Please enter the URL of your CTF Proxy Dashboard API server."
					}
					type="error"
					showIcon
				/>

				<Form
					form={form}
					layout="vertical"
					initialValues={{
						url: currentUrl,
						token: localStorage.getItem("apiToken") || "",
					}}
					onFinish={handleSubmit}
				>
					<Form.Item
						name="url"
						label="API Server URL"
						rules={[
							{ required: true, message: "Please enter API server URL" },
							{ type: "url", message: "Please enter a valid URL" },
						]}
						help="Enter the full URL of your backend server (e.g., http://localhost:48955)"
					>
						<Input placeholder="http://localhost:48955" size="large" />
					</Form.Item>

					<Form.Item
						name="token"
						label="API Token"
						rules={[{ required: true, message: "Please enter API token" }]}
						help="Enter the API token from your CTF Proxy configuration"
					>
						<Input.Password placeholder="Enter your API token" size="large" />
					</Form.Item>

					{testResult && (
						<Alert
							message={testResult.success ? "Success" : "Test Failed"}
							description={testResult.message}
							type={testResult.success ? "success" : "error"}
							showIcon
							style={{ marginBottom: 16 }}
						/>
					)}

					<Space style={{ width: "100%", justifyContent: "flex-end" }}>
						<Button
							onClick={() => {
								const url = form.getFieldValue("url");
								const token = form.getFieldValue("token");
								if (url && token) testConnection(url, token);
							}}
							loading={testing}
						>
							Test Connection
						</Button>
						<Button
							type="primary"
							htmlType="submit"
							disabled={!testResult?.success}
						>
							Save & Connect
						</Button>
					</Space>
				</Form>
			</Space>
		</Modal>
	);
}
