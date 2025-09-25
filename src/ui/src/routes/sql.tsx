import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect } from "react";
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
	ConsoleSqlOutlined,
	OpenAIOutlined,
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
	const [executionTime, setExecutionTime] = useState<number | null>(null);
	const [timeout, setTimeout] = useState<number>(10);
	const [aiModalVisible, setAiModalVisible] = useState(false);
	const [aiQuery, setAiQuery] = useState("");
	const [schema, setSchema] = useState<string>("");

	useEffect(() => {
		fetchSchema();
	}, []);

	const fetchSchema = async () => {
		try {
			const apiHost =
				localStorage.getItem("apiHost") || "http://localhost:8080";
			const response = await fetch(`${apiHost}/api/sql/schema`);
			if (response.ok) {
				const data = await response.json();
				setSchema(data.schema);
			}
		} catch (err) {
			console.error("Failed to fetch schema:", err);
		}
	};

	const executeQuery = async () => {
		setLoading(true);
		setError(null);
		const startTime = Date.now();

		try {
			const apiHost =
				localStorage.getItem("apiHost") || "http://localhost:8080";
			const response = await fetch(`${apiHost}/api/sql`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ query, timeout }),
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || "Query execution failed");
			}

			const data = await response.json();
			setExecutionTime(Date.now() - startTime);

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
		} catch (err) {
			setError(err instanceof Error ? err.message : "Unknown error occurred");
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
			const apiHost =
				localStorage.getItem("apiHost") || "http://localhost:8080";
			const response = await fetch(`${apiHost}/api/sql/export`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ query, timeout }),
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || "Export failed");
			}

			const blob = await response.blob();
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
		} catch (err) {
			message.error(err instanceof Error ? err.message : "Export failed");
		}
	};

	const clearResults = () => {
		setResults([]);
		setColumns([]);
		setError(null);
		setExecutionTime(null);
	};

	const handleAiGenerate = () => {
		if (!aiQuery.trim()) {
			message.warning("Please describe what query you want to generate");
			return;
		}

		const prompt = `Generate a SQL query for the following database schema:\n\n\`\`\`sql\n${schema}\n\`\`\`\n\nUser request: ${aiQuery}`;
		const encodedPrompt = encodeURIComponent(prompt);
		window.open(`https://chatgpt.com/?prompt=${encodedPrompt}`, "_blank");
		setAiModalVisible(false);
		setAiQuery("");
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
				onOk={handleAiGenerate}
				okText="Generate with ChatGPT"
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
