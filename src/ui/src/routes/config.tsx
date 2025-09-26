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
import { useQuery, useMutation } from "@tanstack/react-query";
import {
	getConfigApiConfigGetOptions,
	saveConfigApiConfigPostMutation,
	validateConfigApiConfigValidatePostMutation,
} from "@/client/@tanstack/react-query.gen";
import { getConfigRevisionApiConfigRevisionFilenameGet } from "@/client/sdk.gen";

const { Text } = Typography;

export const Route = createFileRoute("/config")({
	component: ConfigEditor,
});

interface ConfigRevision {
	filename: string;
	timestamp: string;
	size: number;
}

function ConfigEditor() {
	const { notification, modal } = App.useApp();
	const [configContent, setConfigContent] = useState<string>("");
	const [originalContent, setOriginalContent] = useState<string>("");
	const [revisions, setRevisions] = useState<ConfigRevision[]>([]);
	const [isModified, setIsModified] = useState(false);
	const [isValidating, setIsValidating] = useState(false);
	const [drawerOpen, setDrawerOpen] = useState(false);
	const [selectedRevision, setSelectedRevision] = useState<string | null>(null);
	const [revisionContent, setRevisionContent] = useState<string>("");
	const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

	const {
		data: configData,
		isLoading,
		refetch,
	} = useQuery({
		...getConfigApiConfigGetOptions(),
		refetchInterval: false,
	});

	useEffect(() => {
		if (configData) {
			setConfigContent(configData.content);
			setOriginalContent(configData.content);
			setRevisions(configData.revisions || []);
			setIsModified(false);
		}
	}, [configData]);

	const handleEditorChange = (value: string | undefined) => {
		if (value !== undefined) {
			setConfigContent(value);
			setIsModified(value !== originalContent);
		}
	};

	const validateMutation = useMutation({
		...validateConfigApiConfigValidatePostMutation(),
		onSuccess: (result) => {
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
		},
		onError: () => {
			notification.error({
				message: "Validation Failed",
				description: "Failed to validate configuration",
			});
		},
	});

	const saveValidateMutation = useMutation({
		...validateConfigApiConfigValidatePostMutation(),
		onError: () => {
			notification.error({
				message: "Validation Failed",
				description: "Failed to validate configuration",
			});
		},
	});

	const handleValidate = () => {
		validateMutation.mutate({ body: { content: configContent } });
	};

	const saveMutation = useMutation({
		...saveConfigApiConfigPostMutation(),
		onSuccess: (result) => {
			notification.success({
				message: "Configuration Saved",
				description: result.message || "Configuration saved successfully",
			});
			setOriginalContent(configContent);
			setIsModified(false);
			refetch();
		},
		onError: (error: any) => {
			if (error?.validation_errors) {
				notification.error({
					message: "Validation Failed",
					description: error.validation_errors.join(", "),
				});
			} else {
				notification.error({
					message: "Save Failed",
					description: error?.detail || "Failed to save configuration",
				});
			}
		},
	});

	const handleSave = async () => {
		const hide = message.loading("Validating configuration...", 0);
		try {
			const validationResult = await saveValidateMutation.mutateAsync({
				body: { content: configContent },
			});
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
					onOk: () => saveMutation.mutate({ body: { content: configContent } }),
					okText: "Save Anyway",
					okType: "danger",
				});
				return;
			}
			saveMutation.mutate({ body: { content: configContent } });
		} catch (error) {
			hide();
			message.error("Failed to validate configuration");
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

	const handleFetchRevision = async (filename: string) => {
		setSelectedRevision(filename);
		try {
			const { data } = await getConfigRevisionApiConfigRevisionFilenameGet({
				path: { filename },
			});
			setRevisionContent(data.content);
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
							loading={validateMutation.isPending}
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
							loading={saveMutation.isPending}
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
										onClick={() => handleFetchRevision(revision.filename)}
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
