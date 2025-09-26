import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
	getSqlSchemaApiSqlSchemaGetOptions,
	executeSqlApiSqlPostMutation,
	exportSqlCsvApiSqlExportPostMutation,
} from "@/client/@tanstack/react-query.gen";
import {
	Button,
	Input,
	Table,
	Space,
	Card,
	message,
	Typography,
	InputNumber,
	Modal,
} from "antd";
import {
	PlayCircleOutlined,
	DownloadOutlined,
	ClearOutlined,
	OpenAIOutlined,
	CopyOutlined,
} from "@ant-design/icons";

const { TextArea } = Input;
const { Text } = Typography;

export const Route = createFileRoute("/sql")({
	component: SqlExecutor,
	staticData: {
		breadcrumb: "SQL Query",
	},
});

function SqlExecutor() {
	const [query, setQuery] = useState("SELECT * FROM http_request LIMIT 100");
	const [results, setResults] = useState<any[]>([]);
	const [columns, setColumns] = useState<any[]>([]);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [queryTime, setQueryTime] = useState<number | null>(null);
	const [totalTime, setTotalTime] = useState<number | null>(null);
	const [timeout, setTimeout] = useState<number>(10);
	const [aiModalVisible, setAiModalVisible] = useState(false);
	const [aiQuery, setAiQuery] = useState("");

	// Fetch schema using React Query
	const { data: schemaData } = useQuery(getSqlSchemaApiSqlSchemaGetOptions());
	const schema = (schemaData as any)?.schema || "";

	// Mutations for SQL operations
	const executeSqlMutation = useMutation(executeSqlApiSqlPostMutation());
	const exportCsvMutation = useMutation(exportSqlCsvApiSqlExportPostMutation());

	const executeQuery = async () => {
		setLoading(true);
		setError(null);
		const startTime = Date.now();

		try {
			const result = await executeSqlMutation.mutateAsync({
				body: { query, timeout },
			});
			const data = result as any;
			const totalTimeMs = Date.now() - startTime;
			setTotalTime(totalTimeMs);
			setQueryTime(data.query_time || null);

			if (data.rows && data.rows.length > 0) {
				const firstRow = data.rows[0];
				const cols = Object.keys(firstRow).map((key) => ({
					title: key,
					dataIndex: key,
					key: key,
					ellipsis: true,
					render: (text: any) => {
						if (text === null) return <Text type="secondary">NULL</Text>;
						if (typeof text === "boolean") return text ? "true" : "false";
						if (typeof text === "object") return JSON.stringify(text);
						return String(text);
					},
				}));
				setColumns(cols);
				setResults(
					data.rows.map((row: any, index: number) => ({ ...row, key: index })),
				);
			} else {
				setColumns([]);
				setResults([]);
				message.info("Query executed successfully but returned no rows");
			}
		} catch (err: any) {
			let errorMessage = "Unknown error occurred";
			if (err?.body?.detail) {
				errorMessage =
					typeof err.body.detail === "object"
						? JSON.stringify(err.body.detail)
						: err.body.detail;
			} else if (err?.message) {
				errorMessage = err.message;
			} else if (err) {
				errorMessage = err.toString();
			}
			setError(errorMessage);
			setResults([]);
			setColumns([]);
		} finally {
			setLoading(false);
		}
	};

	const exportToCsv = async () => {
		if (!query.trim()) {
			message.warning("No query to export");
			return;
		}

		try {
			const result = await exportCsvMutation.mutateAsync({
				body: { query, timeout },
			});

			// The mutation returns the blob data, need to handle download
			const blob = new Blob([result as any], { type: "text/csv" });
			const url = URL.createObjectURL(blob);
			const link = document.createElement("a");
			link.setAttribute("href", url);
			link.setAttribute("download", `query_results_${Date.now()}.csv`);
			link.style.display = "none";
			document.body.appendChild(link);
			link.click();
			document.body.removeChild(link);
			URL.revokeObjectURL(url);
			message.success("Results exported to CSV");
		} catch (err: any) {
			let errorMessage = "Export failed";
			if (err?.body?.detail) {
				errorMessage =
					typeof err.body.detail === "object"
						? JSON.stringify(err.body.detail)
						: err.body.detail;
			} else if (err?.message) {
				errorMessage = err.message;
			} else if (err) {
				errorMessage = err.toString();
			}
			message.error(errorMessage);
		}
	};

	const clearResults = () => {
		setResults([]);
		setColumns([]);
		setError(null);
		setQueryTime(null);
		setTotalTime(null);
	};

	const handleAiGenerate = () => {
		if (!aiQuery.trim()) {
			message.warning("Please describe what query you want to generate");
			return;
		}

		const prompt = `Read the database schema from this link: https://raw.githubusercontent.com/soon/ctf-proxy/main/src/ctf_proxy/db/schema.sql\n\nThen generate a SQL query for the following request: ${aiQuery}`;
		const encodedPrompt = encodeURIComponent(prompt);
		window.open(`https://chatgpt.com/?q=${encodedPrompt}`, "_blank");
		setAiModalVisible(false);
		setAiQuery("");
	};

	const handleCopyPrompt = () => {
		if (!aiQuery.trim()) {
			message.warning("Please describe what query you want to generate");
			return;
		}

		const prompt = `Generate a SQL query for the following database schema:\n\n\`\`\`sql\n${schema}\n\`\`\`\n\nUser request: ${aiQuery}`;
		navigator.clipboard.writeText(prompt).then(
			() => {
				message.success("Prompt copied to clipboard!");
				setAiModalVisible(false);
				setAiQuery("");
			},
			() => {
				message.error("Failed to copy prompt");
			},
		);
	};

	return (
		<div className="space-y-6">
			<Card
				title={
					<div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
						<span>SQL Query Executor</span>
						<Button
							icon={<OpenAIOutlined />}
							onClick={() => setAiModalVisible(true)}
							size="small"
						>
							AI Generate
						</Button>
					</div>
				}
				size="small"
			>
				<Space direction="vertical" style={{ width: "100%" }}>
					<TextArea
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						placeholder="Enter SQL query..."
						rows={6}
						style={{ fontFamily: "monospace" }}
					/>
					<div
						style={{
							display: "flex",
							justifyContent: "space-between",
							alignItems: "center",
						}}
					>
						<Space>
							<Button
								type="primary"
								icon={<PlayCircleOutlined />}
								onClick={executeQuery}
								loading={loading}
							>
								Execute Query
							</Button>
							<Button
								icon={<DownloadOutlined />}
								onClick={exportToCsv}
								disabled={!query.trim()}
							>
								Export CSV
							</Button>
							<Button icon={<ClearOutlined />} onClick={clearResults}>
								Clear
							</Button>
						</Space>
						<Space align="center">
							<Text>Timeout:</Text>
							<InputNumber
								min={1}
								max={60}
								value={timeout}
								onChange={(value) => setTimeout(value || 10)}
								addonAfter="s"
								style={{ width: 100 }}
							/>
						</Space>
					</div>
					{executionTime !== null && (
						<Text type="secondary" className="text-xs">
							Query executed in {executionTime}ms
						</Text>
					)}
				</Space>
			</Card>

			{error && (
				<Card
					size="small"
					style={{ backgroundColor: "#fff2f0", borderColor: "#ffccc7" }}
				>
					<Text type="danger">{error}</Text>
				</Card>
			)}

			{results.length > 0 && (
				<Card
					title={`Results (${results.length} row${results.length !== 1 ? "s" : ""})`}
					size="small"
					styles={{ body: { padding: "8px" } }}
					style={{ marginTop: "24px" }}
				>
					<Table
						columns={columns}
						dataSource={results}
						size="small"
						scroll={{ x: true, y: 600 }}
						pagination={{
							defaultPageSize: 50,
							showSizeChanger: true,
							pageSizeOptions: ["10", "25", "50", "100", "500"],
							showTotal: (total) => `Total ${total} rows`,
						}}
					/>
				</Card>
			)}

			<Modal
				title="Generate SQL Query with AI"
				open={aiModalVisible}
				onCancel={() => setAiModalVisible(false)}
				footer={[
					<Button key="cancel" onClick={() => setAiModalVisible(false)}>
						Cancel
					</Button>,
					<Button key="copy" icon={<CopyOutlined />} onClick={handleCopyPrompt}>
						Copy Prompt
					</Button>,
					<Button
						key="generate"
						type="primary"
						icon={<OpenAIOutlined />}
						onClick={handleAiGenerate}
					>
						Generate with ChatGPT
					</Button>,
				]}
			>
				<Space direction="vertical" style={{ width: "100%" }}>
					<Text>Describe the query you want to generate:</Text>
					<TextArea
						value={aiQuery}
						onChange={(e) => setAiQuery(e.target.value)}
						placeholder="e.g., Find all requests with status 500 in the last hour"
						rows={4}
					/>
					<Text type="secondary" className="text-xs">
						This will open ChatGPT with your request and the database schema to
						help generate the SQL query.
					</Text>
				</Space>
			</Modal>
		</div>
	);
}
