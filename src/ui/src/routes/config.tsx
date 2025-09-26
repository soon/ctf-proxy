import { useState, useRef, useEffect } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { createPortal } from "react-dom";
import {
	Button,
	Space,
	Drawer,
	List,
	Typography,
	Tag,
	message,
	Modal,
	Spin,
	Empty,
	Card,
	App,
} from "antd";
import {
	SaveOutlined,
	ReloadOutlined,
	HistoryOutlined,
	CheckCircleOutlined,
	CloseCircleOutlined,
	FileTextOutlined,
	ClockCircleOutlined,
	ExclamationCircleOutlined,
} from "@ant-design/icons";
import Editor from "@monaco-editor/react";
import type { editor } from "monaco-editor";

const { Text } = Typography;

export const Route = createFileRoute("/config")({
	component: ConfigEditor,
});

interface ConfigRevision {
	filename: string;
	timestamp: string;
	size: number;
}

interface ConfigResponse {
	content: string;
	revisions: ConfigRevision[];
}

interface ValidationResult {
	valid: boolean;
	errors: string[];
}

function ConfigEditor() {
	const { notification, modal } = App.useApp();
	const [configContent, setConfigContent] = useState<string>("");
	const [originalContent, setOriginalContent] = useState<string>("");
	const [revisions, setRevisions] = useState<ConfigRevision[]>([]);
	const [isModified, setIsModified] = useState(false);
	const [isSaving, setIsSaving] = useState(false);
	const [isLoading, setIsLoading] = useState(true);
	const [isValidating, setIsValidating] = useState(false);
	const [drawerOpen, setDrawerOpen] = useState(false);
	const [selectedRevision, setSelectedRevision] = useState<string | null>(null);
	const [revisionContent, setRevisionContent] = useState<string>("");
	const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

	const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8082";

	const fetchConfig = async () => {
		setIsLoading(true);
		try {
			const response = await fetch(`${apiUrl}/api/config`);
			if (!response.ok) throw new Error("Failed to fetch config");
			const data: ConfigResponse = await response.json();
			setConfigContent(data.content);
			setOriginalContent(data.content);
			setRevisions(data.revisions || []);
			setIsModified(false);
		} catch (error) {
			message.error("Failed to load configuration");
			console.error(error);
		} finally {
			setIsLoading(false);
		}
	};

	useEffect(() => {
		fetchConfig();
	}, []);

	const handleEditorChange = (value: string | undefined) => {
		if (value !== undefined) {
			setConfigContent(value);
			setIsModified(value !== originalContent);
		}
	};

	const handleValidate = async () => {
		setIsValidating(true);
		try {
			const response = await fetch(`${apiUrl}/api/config/validate`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ content: configContent }),
			});
			const result: ValidationResult = await response.json();
			if (result.valid) {
				notification.success({
					message: "Configuration Valid",
					description: "The configuration is valid and can be saved.",
				});
			} else {
				notification.error({
					message: "Validation Errors",
					description: (
						<ul style={{ margin: 0, paddingLeft: 20 }}>
							{result.errors.map((error, i) => (
								<li key={i}>{error}</li>
							))}
						</ul>
					),
					duration: 0,
				});
			}
		} catch (error) {
			notification.error({
				message: "Validation Failed",
				description: "Failed to validate configuration",
			});
		} finally {
			setIsValidating(false);
		}
	};

	const handleSave = async () => {
		const hide = message.loading("Validating configuration...", 0);
		try {
			const validateResponse = await fetch(`${apiUrl}/api/config/validate`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ content: configContent }),
			});
			const validationResult = await validateResponse.json();
			hide();

			if (!validationResult.valid) {
				modal.confirm({
					title: "Invalid Configuration",
					content: (
						<div>
							<p>The configuration has validation errors:</p>
							<ul style={{ color: "red" }}>
								{validationResult.errors.map((error: string, i: number) => (
									<li key={i}>{error}</li>
								))}
							</ul>
							<p>Do you want to save anyway?</p>
						</div>
					),
					onOk: () => saveConfig(),
					okText: "Save Anyway",
					okType: "danger",
				});
				return;
			}
			await saveConfig();
		} catch (error) {
			hide();
			message.error("Failed to validate configuration");
		}
	};

	const saveConfig = async () => {
		setIsSaving(true);
		const hide = message.loading("Saving configuration...", 0);
		try {
			const response = await fetch(`${apiUrl}/api/config`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ content: configContent }),
			});
			hide();

			if (!response.ok) {
				const error = await response.json();
				if (error.detail?.validation_errors) {
					notification.error({
						message: "Validation Failed",
						description: error.detail.validation_errors.join(", "),
					});
				} else {
					notification.error({
						message: "Save Failed",
						description: error.detail || "Failed to save configuration",
					});
				}
				setIsSaving(false);
				return;
			}

			const result = await response.json();
			notification.success({
				message: "Configuration Saved",
				description: result.message || "Configuration saved successfully",
			});
			setOriginalContent(configContent);
			setIsModified(false);
			await fetchConfig();
		} catch (error) {
			hide();
			notification.error({
				message: "Save Failed",
				description: "Failed to save configuration",
			});
			console.error(error);
		} finally {
			setIsSaving(false);
		}
	};

	const handleReset = () => {
		modal.confirm({
			title: "Reset Changes",
			content: "Are you sure you want to discard all unsaved changes?",
			onOk: () => {
				setConfigContent(originalContent);
				setIsModified(false);
			},
		});
	};

	const fetchRevisionContent = async (filename: string) => {
		try {
			const response = await fetch(`${apiUrl}/api/config/revision/${filename}`);
			if (!response.ok) throw new Error("Failed to fetch revision");
			const data = await response.json();
			setRevisionContent(data.content);
			setSelectedRevision(filename);
		} catch (error) {
			message.error("Failed to load revision");
		}
	};

	const handleRestoreRevision = () => {
		if (!selectedRevision) return;

		modal.confirm({
			title: "Restore Revision",
			content: (
				<div>
					<p>
						This will replace the current configuration with the selected
						revision.
					</p>
					<p>
						<strong>Note:</strong> This will NOT save the configuration
						automatically.
					</p>
					<p>You can review the changes and save manually.</p>
				</div>
			),
			onOk: () => {
				setConfigContent(revisionContent);
				setIsModified(true);
				setDrawerOpen(false);
				message.success(
					"Revision loaded. Remember to save if you want to keep these changes.",
				);
			},
		});
	};

	const formatTimestamp = (timestamp: string) => {
		const date = new Date(
			timestamp.replace(
				/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/,
				"$1-$2-$3T$4:$5:$6",
			),
		);
		return date.toLocaleString();
	};

	const formatSize = (bytes: number) => {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	};

	if (isLoading) {
		return (
			<div
				style={{
					display: "flex",
					justifyContent: "center",
					alignItems: "center",
					height: "calc(100vh - 200px)",
				}}
			>
				<Spin size="large" />
			</div>
		);
	}

	const pageActions = document.getElementById("page-actions");

	return (
		<>
			{pageActions &&
				createPortal(
					<Space>
						{isModified && <Tag color="orange">Modified</Tag>}
						<Button
							icon={<CheckCircleOutlined />}
							onClick={handleValidate}
							loading={isValidating}
						>
							Validate
						</Button>
						<Button
							icon={<ReloadOutlined />}
							onClick={handleReset}
							disabled={!isModified}
						>
							Reset
						</Button>
						<Button
							icon={<HistoryOutlined />}
							onClick={() => setDrawerOpen(true)}
						>
							Revisions ({revisions.length})
						</Button>
						<Button
							type="primary"
							icon={<SaveOutlined />}
							onClick={handleSave}
							loading={isSaving}
							disabled={!isModified}
						>
							Save
						</Button>
					</Space>,
					pageActions,
				)}
			<div>
				<div style={{ border: "1px solid #d9d9d9", borderRadius: 4 }}>
					<Editor
						height="calc(100vh - 200px)"
						defaultLanguage="yaml"
						value={configContent}
						onChange={handleEditorChange}
						onMount={(editor) => {
							editorRef.current = editor;
						}}
						options={{
							minimap: { enabled: false },
							fontSize: 14,
							wordWrap: "on",
							lineNumbers: "on",
							scrollBeyondLastLine: false,
							automaticLayout: true,
						}}
						theme="vs-light"
					/>
				</div>
			</div>

			<Drawer
				title="Configuration Revisions"
				placement="right"
				onClose={() => setDrawerOpen(false)}
				open={drawerOpen}
				width={600}
			>
				{revisions.length === 0 ? (
					<Empty description="No revisions available" />
				) : (
					<List
						dataSource={revisions}
						renderItem={(revision) => (
							<List.Item
								key={revision.filename}
								actions={[
									<Button
										key="view"
										size="small"
										onClick={() => fetchRevisionContent(revision.filename)}
									>
										View
									</Button>,
								]}
								style={{
									background:
										selectedRevision === revision.filename
											? "#f0f2f5"
											: undefined,
									padding: "12px",
									borderRadius: 4,
									marginBottom: 8,
								}}
							>
								<List.Item.Meta
									avatar={<ClockCircleOutlined style={{ fontSize: 20 }} />}
									title={formatTimestamp(revision.timestamp)}
									description={
										<Space>
											<Text type="secondary">{revision.filename}</Text>
											<Text type="secondary">•</Text>
											<Text type="secondary">{formatSize(revision.size)}</Text>
										</Space>
									}
								/>
							</List.Item>
						)}
					/>
				)}

				{selectedRevision && revisionContent && (
					<Card
						title={`Revision: ${selectedRevision}`}
						style={{ marginTop: 16 }}
						extra={
							<Button
								type="primary"
								icon={<ReloadOutlined />}
								onClick={handleRestoreRevision}
							>
								Restore This Version
							</Button>
						}
					>
						<div
							style={{
								border: "1px solid #d9d9d9",
								borderRadius: 4,
								maxHeight: 400,
								overflow: "auto",
							}}
						>
							<Editor
								height="400px"
								defaultLanguage="yaml"
								value={revisionContent}
								options={{
									readOnly: true,
									minimap: { enabled: false },
									fontSize: 12,
									wordWrap: "on",
									lineNumbers: "on",
									scrollBeyondLastLine: false,
								}}
								theme="vs-light"
							/>
						</div>
					</Card>
				)}
			</Drawer>
		</>
	);
}
