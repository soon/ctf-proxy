import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
	getServiceByPortApiServicesPortGetOptions,
	getServiceRequestsApiServicesPortRequestsGetOptions,
	getTcpConnectionsApiServicesPortTcpConnectionsGetOptions,
	getServiceFlagTimeStatsApiServicesPortFlagTimeStatsGetOptions,
	getServiceRequestTimeStatsApiServicesPortRequestTimeStatsGetOptions,
} from "@/client/@tanstack/react-query.gen";
import {
	getServiceRequestsApiServicesPortRequestsGet,
	getRequestRawApiRequestsRequestIdRawGet,
} from "@/client/sdk.gen";
import {
	Card,
	Table,
	Tag,
	Button,
	Input,
	Row,
	Col,
	Statistic,
	Space,
	Empty,
	Spin,
	Modal,
	List,
	Typography,
} from "antd";
import {
	ReloadOutlined,
	FlagOutlined,
	ApiOutlined,
	AlertOutlined,
	LinkOutlined,
	FilterOutlined,
	ClearOutlined,
	LineChartOutlined,
	SearchOutlined,
	FileTextOutlined,
	WarningOutlined,
	CodeOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useState, useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { SparklineChart } from "@/components/SparklineChart";

const { Search } = Input;
const { Text } = Typography;

export const Route = createFileRoute("/service/$port/")({
	component: ServiceDetail,
	staticData: {
		breadcrumb: "Service",
	},
});

function formatBytes(bytes: number): string {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	if (bytes < 1024 * 1024 * 1024)
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function ServiceDetail() {
	const { port } = Route.useParams();
	const portNumber = parseInt(port);
	const navigate = useNavigate();
	const [currentPage, setCurrentPage] = useState(1);
	const [pageSize, setPageSize] = useState(30);
	const [filters, setFilters] = useState<{
		filter_path?: string;
		filter_method?: string;
		filter_status?: number;
		filter_blocked?: boolean;
	}>({});
	const [searchValue, setSearchValue] = useState("");
	const [alertsModalVisible, setAlertsModalVisible] = useState(false);
	const [rawRequestModalVisible, setRawRequestModalVisible] = useState(false);
	const [selectedRequestId, setSelectedRequestId] = useState<number | null>(
		null,
	);
	const [rawRequestData, setRawRequestData] = useState<any>(null);
	const [loadingRawData, setLoadingRawData] = useState(false);
	const [newRequestsAvailable, setNewRequestsAvailable] = useState(0);
	const lastRequestCountRef = useRef<number>(0);
	const isRefreshingRef = useRef<boolean>(false);

	const {
		data: service,
		isLoading: serviceLoading,
		refetch: refetchService,
	} = useQuery({
		...getServiceByPortApiServicesPortGetOptions({
			path: { port: portNumber },
		}),
		refetchInterval: 5000,
	});

	const isTcpService = service?.type === "tcp";
	const [hoverTimestamp, setHoverTimestamp] = useState<number | null>(null);
	const [windowMinutes, setWindowMinutes] = useState(60);

	// Fetch time stats for charts
	const { data: flagTimeStats, refetch: refetchFlagStats } = useQuery({
		...getServiceFlagTimeStatsApiServicesPortFlagTimeStatsGetOptions({
			path: { port: portNumber },
			query: { window_minutes: windowMinutes },
		}),
		enabled: !!service && !isTcpService,
		refetchInterval: 30000,
	});

	const { data: requestTimeStats, refetch: refetchRequestStats } = useQuery({
		...getServiceRequestTimeStatsApiServicesPortRequestTimeStatsGetOptions({
			path: { port: portNumber },
			query: { window_minutes: windowMinutes },
		}),
		enabled: !!service && !isTcpService,
		refetchInterval: 30000,
	});

	const {
		data: requestsData,
		isLoading: requestsLoading,
		refetch: refetchRequests,
		isFetching: requestsFetching,
	} = useQuery({
		...getServiceRequestsApiServicesPortRequestsGetOptions({
			path: { port: portNumber },
			query: {
				page: currentPage,
				page_size: pageSize,
				...filters,
			},
		}),
		enabled: !isTcpService && !!service,
	});

	// Fetch TCP connections for TCP services
	const {
		data: tcpConnectionsData,
		isLoading: tcpConnectionsLoading,
		refetch: refetchTcpConnections,
	} = useQuery({
		...getTcpConnectionsApiServicesPortTcpConnectionsGetOptions({
			path: { port: portNumber },
			query: {
				page: currentPage,
				page_size: pageSize,
			},
		}),
		enabled: isTcpService && !!service,
	});

	const handleSearch = useCallback((value: string) => {
		const trimmed = value.trim();
		setCurrentPage(1); // Reset to first page on new search
		if (!trimmed) {
			setFilters({});
			return;
		}

		// Parse filter commands similar to CLI
		if (trimmed.startsWith("/")) {
			setFilters({ filter_path: trimmed });
		} else if (trimmed.match(/^[1-5]\d{2}$/)) {
			setFilters({ filter_status: parseInt(trimmed) });
		} else if (
			["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"].includes(
				trimmed.toUpperCase(),
			)
		) {
			setFilters({ filter_method: trimmed.toUpperCase() });
		} else if (trimmed.toLowerCase() === "blocked") {
			setFilters({ filter_blocked: true });
		} else {
			// Default to path contains
			setFilters({ filter_path: trimmed });
		}
	}, []);

	// Check for new requests periodically
	useEffect(() => {
		if (!isTcpService && service) {
			const checkInterval = setInterval(async () => {
				// Skip check if currently fetching or refreshing
				if (requestsFetching || isRefreshingRef.current) {
					return;
				}

				try {
					const { data } = await getServiceRequestsApiServicesPortRequestsGet({
						path: { port: portNumber },
						query: { page: 1, page_size: 1 },
					});
					if (
						lastRequestCountRef.current > 0 &&
						data.total > lastRequestCountRef.current
					) {
						setNewRequestsAvailable(data.total - lastRequestCountRef.current);
					}
				} catch (error) {
					console.error("Failed to check for new requests:", error);
				}
			}, 5000);

			return () => clearInterval(checkInterval);
		}
	}, [isTcpService, service, portNumber, requestsFetching]);

	// Initialize and update last request count when data changes
	useEffect(() => {
		if (requestsData?.total !== undefined) {
			// Only update if this is the first load or after a manual refresh
			if (lastRequestCountRef.current === 0 || isRefreshingRef.current) {
				lastRequestCountRef.current = requestsData.total;
				isRefreshingRef.current = false;
			}
		}
	}, [requestsData]);

	const clearFilters = () => {
		setFilters({});
		setSearchValue("");
		setCurrentPage(1);
	};

	const handlePageChange = (page: number, newPageSize?: number) => {
		setCurrentPage(page);
		if (newPageSize && newPageSize !== pageSize) {
			setPageSize(newPageSize);
		}
	};

	const httpColumns: ColumnsType<any> = [
		{
			title: "ID",
			dataIndex: "id",
			key: "id",
			width: 60,
		},
		{
			title: "Time",
			dataIndex: "timestamp",
			key: "timestamp",
			width: 80,
			render: (timestamp: string) =>
				new Date(timestamp).toLocaleTimeString("en-GB", {
					hour: "2-digit",
					minute: "2-digit",
					second: "2-digit",
				}),
		},
		{
			title: "Method",
			dataIndex: "method",
			key: "method",
			width: 70,
			render: (method: string) => (
				<Tag
					color={
						method === "GET"
							? "blue"
							: method === "POST"
								? "green"
								: method === "PUT"
									? "orange"
									: method === "DELETE"
										? "red"
										: "default"
					}
					className="text-xs"
				>
					{method}
				</Tag>
			),
		},
		{
			title: "Path",
			dataIndex: "path",
			key: "path",
			ellipsis: true,
			render: (path: string) => (
				<span className="font-mono text-xs">{path}</span>
			),
		},
		{
			title: "Status",
			dataIndex: "status",
			key: "status",
			width: 60,
			render: (status: number | null) =>
				status ? (
					<Tag
						color={
							status >= 200 && status < 300
								? "success"
								: status >= 300 && status < 400
									? "processing"
									: status >= 400 && status < 500
										? "warning"
										: status >= 500
											? "error"
											: "default"
						}
						className="text-xs"
					>
						{status}
					</Tag>
				) : (
					<span className="text-gray-400 text-xs">N/A</span>
				),
		},
		{
			title: "Flags",
			key: "flags",
			width: 100,
			render: (_, record: any) => {
				if (!record.request_flags && !record.response_flags) return null;
				return (
					<Space size={2}>
						{record.request_flags > 0 && (
							<Tag icon={<FlagOutlined />} color="blue" className="text-xs">
								{record.request_flags > 1 && `${record.request_flags} `}REQ
							</Tag>
						)}
						{record.response_flags > 0 && (
							<Tag icon={<FlagOutlined />} color="red" className="text-xs">
								{record.response_flags > 1 && `${record.response_flags} `}RESP
							</Tag>
						)}
					</Space>
				);
			},
		},
		{
			title: "Session",
			key: "links",
			width: 80,
			render: (_, record: any) => {
				const totalLinks = record.total_links || 0;

				if (totalLinks === 0) return null;

				if (totalLinks === 1) {
					// Single request in session
					return <div className="text-gray-400 text-xs">Standalone</div>;
				}

				// Multiple requests in session
				return (
					<div className="flex items-center gap-1">
						<svg
							width="40"
							height="20"
							viewBox="0 0 40 20"
							className="inline-block"
						>
							<circle cx="10" cy="10" r="3" fill="#3b82f6" />
							<line
								x1="13"
								y1="10"
								x2="27"
								y2="10"
								stroke="#3b82f6"
								strokeWidth="2"
							/>
							<circle cx="30" cy="10" r="3" fill="#3b82f6" />
						</svg>
						<span className="text-xs text-blue-500 font-medium">
							{totalLinks}
						</span>
					</div>
				);
			},
		},
		{
			title: "Blocked",
			key: "blocked",
			width: 70,
			render: (_, record: any) =>
				record.is_blocked ? (
					<Tag color="error" className="text-xs">
						BLOCKED
					</Tag>
				) : null,
		},
		{
			title: "Raw",
			key: "actions",
			width: 60,
			render: (_, record: any) => (
				<Button
					size="small"
					icon={<CodeOutlined />}
					onClick={async (e) => {
						e.stopPropagation();
						setSelectedRequestId(record.id);
						setLoadingRawData(true);
						setRawRequestModalVisible(true);

						try {
							const { data } = await getRequestRawApiRequestsRequestIdRawGet({
								path: { request_id: record.id },
							});
							setRawRequestData(data);
						} catch (error) {
							setRawRequestData({ error: String(error) });
						} finally {
							setLoadingRawData(false);
						}
					}}
				/>
			),
		},
	];

	// TCP Connections columns
	const tcpColumns: ColumnsType<any> = [
		{
			title: "ID",
			dataIndex: "id",
			key: "id",
			width: 60,
		},
		{
			title: "Conn ID",
			dataIndex: "connection_id",
			key: "connection_id",
			width: 80,
			render: (id: number) => <span className="font-mono text-xs">{id}</span>,
		},
		{
			title: "Time",
			dataIndex: "timestamp",
			key: "timestamp",
			width: 80,
			render: (timestamp: string) =>
				new Date(timestamp).toLocaleTimeString("en-GB", {
					hour: "2-digit",
					minute: "2-digit",
					second: "2-digit",
				}),
		},
		{
			title: "Bytes In",
			dataIndex: "bytes_in",
			key: "bytes_in",
			width: 90,
			render: (bytes: number) => {
				if (bytes < 1024) return `${bytes} B`;
				if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
				return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
			},
		},
		{
			title: "Bytes Out",
			dataIndex: "bytes_out",
			key: "bytes_out",
			width: 90,
			render: (bytes: number) => {
				if (bytes < 1024) return `${bytes} B`;
				if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
				return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
			},
		},
		{
			title: "Duration",
			dataIndex: "duration_ms",
			key: "duration_ms",
			width: 80,
			render: (ms: number | null) =>
				ms !== null ? (
					<span className="text-xs">
						{ms >= 1000
							? `${(ms / 1000).toFixed(2)}s`
							: ms >= 1
								? `${ms.toFixed(1)}ms`
								: `${(ms * 1000000).toFixed(0)}ns`}
					</span>
				) : (
					<span className="text-gray-400 text-xs">Active</span>
				),
		},
		{
			title: "Flags In",
			dataIndex: "flags_in",
			key: "flags_in",
			width: 80,
			render: (count: number) =>
				count > 0 ? (
					<Tag icon={<FlagOutlined />} color="blue" className="text-xs">
						IN: {count}
					</Tag>
				) : null,
		},
		{
			title: "Flags Out",
			dataIndex: "flags_out",
			key: "flags_out",
			width: 85,
			render: (count: number) =>
				count > 0 ? (
					<Tag icon={<FlagOutlined />} color="red" className="text-xs">
						OUT: {count}
					</Tag>
				) : null,
		},
		{
			title: "Blocked",
			dataIndex: "is_blocked",
			key: "is_blocked",
			width: 70,
			render: (blocked: boolean) =>
				blocked ? (
					<Tag color="error" className="text-xs">
						BLOCKED
					</Tag>
				) : null,
		},
	];

	if (serviceLoading || !service) {
		return (
			<div className="flex justify-center items-center h-64">
				<Spin size="large" tip="Loading service details..." />
			</div>
		);
	}

	const shortName = service.name.substring(0, 4).toUpperCase();

	const controls = (
		<Space size={4}>
			<Search
				placeholder="Filter: /path, 404, GET, blocked"
				allowClear
				enterButton={<FilterOutlined />}
				style={{ width: 250 }}
				value={searchValue}
				onChange={(e) => setSearchValue(e.target.value)}
				onSearch={handleSearch}
			/>
			{Object.keys(filters).length > 0 && (
				<Button icon={<ClearOutlined />} onClick={clearFilters}>
					Clear
				</Button>
			)}
			{isTcpService ? (
				<Button
					icon={<LineChartOutlined />}
					onClick={() => navigate({ to: `/service/${port}/tcp-stats` })}
				>
					TCP Stats
				</Button>
			) : (
				<>
					<Button
						icon={<LineChartOutlined />}
						onClick={() => navigate({ to: `/service/${port}/paths` })}
					>
						Paths
					</Button>
					<Button
						icon={<SearchOutlined />}
						onClick={() => navigate({ to: `/service/${port}/queries` })}
					>
						Queries
					</Button>
					<Button
						icon={<FileTextOutlined />}
						onClick={() => navigate({ to: `/service/${port}/headers` })}
					>
						Headers
					</Button>
				</>
			)}
			<Button
				icon={<ReloadOutlined />}
				onClick={() => {
					refetchService();
					if (isTcpService) {
						refetchTcpConnections();
					} else {
						isRefreshingRef.current = true;
						refetchRequests();
						setNewRequestsAvailable(0);
					}
				}}
			>
				Refresh
			</Button>
		</Space>
	);

	const pageActionsContainer = document.getElementById("page-actions");

	return (
		<div className="space-y-2">
			{pageActionsContainer && createPortal(controls, pageActionsContainer)}
			{/* Stats Overview - More compact */}
			<Row gutter={[8, 8]}>
				<Col xs={24} sm={12}>
					<Card
						size="small"
						bodyStyle={{ padding: "8px" }}
						className="hover:shadow-md transition-shadow"
					>
						{isTcpService ? (
							<Statistic
								title={<span className="text-xs">Connections</span>}
								value={service.stats.tcp_stats?.total_connections || 0}
								prefix={<ApiOutlined className="text-xs" />}
								valueStyle={{ fontSize: 14 }}
							/>
						) : (
							<div>
								<div className="flex justify-between items-center mb-1">
									<span className="text-xs text-gray-500">
										<ApiOutlined className="mr-1" />
										Requests ({service.stats.total_requests.toLocaleString()}{" "}
										total)
									</span>
								</div>
								{requestTimeStats && (
									<SparklineChart
										time_series={requestTimeStats.stats.map((s) => ({
											timestamp: new Date(s.time).getTime(),
											count: s.count,
										}))}
										windowMinutes={requestTimeStats.window_minutes}
										globalHoverTimestamp={hoverTimestamp}
										onHoverChange={setHoverTimestamp}
									/>
								)}
								{service.stats.blocked_requests > 0 && (
									<div className="text-xs text-red-500 mt-1">
										{service.stats.blocked_requests.toLocaleString()} blocked
									</div>
								)}
							</div>
						)}
					</Card>
				</Col>
				<Col xs={24} sm={12}>
					<Card size="small" bodyStyle={{ padding: "8px" }}>
						{isTcpService ? (
							<Statistic
								title={<span className="text-xs">Bytes In/Out</span>}
								value={`${formatBytes(service.stats.tcp_stats?.total_bytes_in || 0)}/${formatBytes(service.stats.tcp_stats?.total_bytes_out || 0)}`}
								valueStyle={{ fontSize: 14 }}
							/>
						) : (
							<div>
								<div className="flex justify-between items-center mb-1">
									<span className="text-xs text-gray-500">
										<FlagOutlined className="mr-1" />
										Flags Written (
										{service.stats.flags_written.toLocaleString()} total)
									</span>
								</div>
								{flagTimeStats && (
									<SparklineChart
										time_series={flagTimeStats.stats.map((s) => ({
											timestamp: new Date(s.time).getTime(),
											count: s.write_count,
										}))}
										windowMinutes={flagTimeStats.window_minutes}
										globalHoverTimestamp={hoverTimestamp}
										onHoverChange={setHoverTimestamp}
									/>
								)}
							</div>
						)}
					</Card>
				</Col>
				<Col xs={24} sm={12}>
					<Card size="small" bodyStyle={{ padding: "8px" }}>
						{!isTcpService && (
							<div>
								<div className="flex justify-between items-center mb-1">
									<span className="text-xs text-gray-500">
										<FlagOutlined className="mr-1" />
										Flags Retrieved (
										{service.stats.flags_retrieved.toLocaleString()} total)
									</span>
								</div>
								{flagTimeStats && (
									<SparklineChart
										time_series={flagTimeStats.stats.map((s) => ({
											timestamp: new Date(s.time).getTime(),
											count: s.read_count,
										}))}
										windowMinutes={flagTimeStats.window_minutes}
										globalHoverTimestamp={hoverTimestamp}
										onHoverChange={setHoverTimestamp}
									/>
								)}
								{service.stats.flags_blocked > 0 && (
									<div className="text-xs text-red-500 mt-1">
										{service.stats.flags_blocked.toLocaleString()} blocked
									</div>
								)}
							</div>
						)}
					</Card>
				</Col>
				<Col xs={12} sm={6}>
					<Card
						size="small"
						bodyStyle={{ padding: "8px", cursor: "pointer" }}
						className="hover:shadow-md transition-shadow"
						onClick={() => setAlertsModalVisible(true)}
					>
						<Statistic
							title={<span className="text-xs">Alerts</span>}
							value={service.stats.alerts_count}
							prefix={<AlertOutlined className="text-xs" />}
							valueStyle={{
								fontSize: 14,
								color: service.stats.alerts_count > 0 ? "#cf1322" : undefined,
							}}
						/>
					</Card>
				</Col>
				<Col xs={12} sm={6}>
					<Card
						size="small"
						bodyStyle={{ padding: "8px", cursor: "pointer" }}
						className="hover:shadow-md transition-shadow"
						onClick={() => navigate({ to: `/service/${port}/paths` })}
					>
						<Statistic
							title={<span className="text-xs">Paths</span>}
							value={service.stats.unique_paths}
							prefix={<LinkOutlined className="text-xs" />}
							valueStyle={{ fontSize: 14 }}
						/>
					</Card>
				</Col>
			</Row>

			{/* New requests notification */}
			{!isTcpService && newRequestsAvailable > 0 && (
				<div className="bg-blue-50 border border-blue-200 rounded px-4 py-2 mb-2 flex justify-between items-center">
					<span className="text-sm">
						<span className="font-medium">
							{newRequestsAvailable.toLocaleString()}
						</span>{" "}
						new request{newRequestsAvailable > 1 ? "s" : ""} available
					</span>
					<Button
						type="primary"
						size="small"
						onClick={() => {
							isRefreshingRef.current = true;
							refetchRequests();
							setNewRequestsAvailable(0);
						}}
					>
						Load New Requests
					</Button>
				</div>
			)}

			{/* Requests Table for HTTP services or TCP Connections Table for TCP services */}
			{isTcpService ? (
				// TCP Connections Table
				tcpConnectionsLoading ? (
					<div className="flex justify-center py-4">
						<Spin />
					</div>
				) : !tcpConnectionsData ? (
					<Empty description="No TCP connections data available" />
				) : tcpConnectionsData.connections.length === 0 ? (
					<Empty description="No TCP connections found" />
				) : (
					<Table
						columns={tcpColumns}
						dataSource={tcpConnectionsData.connections}
						rowKey={(record, index) =>
							`${record.id || index}-${record.timestamp || index}`
						}
						size="small"
						pagination={{
							current: currentPage,
							pageSize: pageSize,
							total: tcpConnectionsData?.total || 0,
							showSizeChanger: true,
							pageSizeOptions: ["10", "20", "30", "50", "100"],
							onChange: handlePageChange,
							showTotal: (total, range) => (
								<span className="text-xs">
									{range[0].toLocaleString()}-{range[1].toLocaleString()} of{" "}
									{total.toLocaleString()} connections
								</span>
							),
						}}
						scroll={{ x: 700 }}
						rowClassName="hover:bg-gray-50 cursor-pointer"
						onRow={(record) => ({
							onClick: () =>
								navigate({
									to: `/service/${port}/tcp-connection/${record.id}`,
								}),
						})}
					/>
				)
			) : // HTTP Requests Table
			requestsLoading ? (
				<div className="flex justify-center py-4">
					<Spin />
				</div>
			) : requestsData?.requests?.length === 0 ? (
				<Empty description="No requests found" />
			) : (
				<Table
					columns={httpColumns}
					dataSource={requestsData?.requests}
					rowKey="id"
					size="small"
					pagination={{
						current: currentPage,
						pageSize: pageSize,
						total: requestsData?.total || 0,
						showSizeChanger: true,
						pageSizeOptions: ["10", "20", "30", "50", "100"],
						onChange: handlePageChange,
						showTotal: (total, range) => (
							<span className="text-xs">
								{range[0].toLocaleString()}-{range[1].toLocaleString()} of{" "}
								{total.toLocaleString()} requests
							</span>
						),
					}}
					scroll={{ x: 700 }}
					rowClassName="hover:bg-gray-50 cursor-pointer"
					onRow={(record) => ({
						onClick: () =>
							navigate({ to: `/service/${port}/request/${record.id}` }),
					})}
				/>
			)}

			{/* Alerts Modal */}
			<Modal
				title={
					<Space>
						<WarningOutlined style={{ color: "#cf1322" }} />
						<span>Recent Alerts</span>
					</Space>
				}
				open={alertsModalVisible}
				onCancel={() => setAlertsModalVisible(false)}
				footer={[
					<Button key="close" onClick={() => setAlertsModalVisible(false)}>
						Close
					</Button>,
				]}
				width={800}
			>
				{service?.stats.recent_alerts &&
				service.stats.recent_alerts.length > 0 ? (
					<List
						dataSource={service.stats.recent_alerts}
						renderItem={(alert: [string, any]) => (
							<List.Item>
								<Space direction="vertical" style={{ width: "100%" }}>
									<Text strong>{alert[0]}</Text>
									{typeof alert[1] === "object" ? (
										<pre className="text-xs bg-gray-100 p-2 rounded overflow-x-auto">
											{JSON.stringify(alert[1], null, 2)}
										</pre>
									) : (
										<Text className="text-sm">{String(alert[1])}</Text>
									)}
								</Space>
							</List.Item>
						)}
					/>
				) : (
					<Empty description="No alerts available" />
				)}
			</Modal>

			{/* Raw Request Modal */}
			<Modal
				title={
					<Space>
						<CodeOutlined />
						<span>Raw Request Data (ID: {selectedRequestId})</span>
					</Space>
				}
				open={rawRequestModalVisible}
				onCancel={() => {
					setRawRequestModalVisible(false);
					setRawRequestData(null);
				}}
				footer={[
					<Button
						key="close"
						onClick={() => {
							setRawRequestModalVisible(false);
							setRawRequestData(null);
						}}
					>
						Close
					</Button>,
				]}
				width={900}
			>
				{loadingRawData ? (
					<div className="flex justify-center py-8">
						<Spin tip="Loading raw data..." />
					</div>
				) : rawRequestData ? (
					rawRequestData.error ? (
						<Text type="danger">{rawRequestData.error}</Text>
					) : (
						<pre className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto max-h-[500px] text-xs font-mono">
							{JSON.stringify(rawRequestData, null, 2)}
						</pre>
					)
				) : (
					<Empty description="No data available" />
				)}
			</Modal>
		</div>
	);
}
