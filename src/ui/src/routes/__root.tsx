import {
	Outlet,
	createRootRouteWithContext,
	useNavigate,
	useLocation,
	useRouterState,
} from "@tanstack/react-router";
import { TanStackRouterDevtoolsPanel } from "@tanstack/react-router-devtools";
import { TanstackDevtools } from "@tanstack/react-devtools";

import TanStackQueryDevtools from "../integrations/tanstack-query/devtools";

import type { QueryClient } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import { getServicesApiServicesGetOptions } from "@/client/@tanstack/react-query.gen";

import { Breadcrumb, Layout, Menu, theme, Spin } from "antd";
import {
	DashboardOutlined,
	ApiOutlined,
	SettingOutlined,
} from "@ant-design/icons";
import { useHealthCheck } from "@/hooks/useHealthCheck";
import { HostConfig } from "@/components/HostConfig";
import SettingsModal from "@/components/SettingsModal";
import { useState } from "react";
import { Button } from "antd";

const { Header, Content, Footer } = Layout;

interface MyRouterContext {
	queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<MyRouterContext>()({
	component: () => {
		const {
			token: { colorBgContainer, borderRadiusLG },
		} = theme.useToken();
		const navigate = useNavigate();
		const location = useLocation();
		const { isHealthy, isChecking, error, apiUrl } = useHealthCheck();
		const [settingsOpen, setSettingsOpen] = useState(false);

		const { data } = useQuery({
			...getServicesApiServicesGetOptions(),
			enabled: isHealthy, // Only query if healthy
			refetchInterval: 30000, // Refresh every 30 seconds
		});

		// Determine selected key based on current path
		const getSelectedKey = () => {
			const path = location.pathname;
			if (path === "/") {
				return "dashboard";
			}
			if (path === "/sql") {
				return "sql";
			}
			const serviceMatch = path.match(/^\/service\/(\d+)/);
			if (serviceMatch) {
				return `service-${serviceMatch[1]}`;
			}
			return "dashboard";
		};

		const menuItems = [
			{
				key: "dashboard",
				label: "Dashboard",
				icon: <DashboardOutlined />,
				onClick: () => navigate({ to: "/" }),
			},
			...(data?.services?.map((service) => ({
				key: `service-${service.port}`,
				label: `${service.name.substring(0, 4).toUpperCase()}:${service.port}`,
				icon: <ApiOutlined />,
				onClick: () => navigate({ to: `/service/${service.port}` }),
			})) || []),
			{
				key: "sql",
				label: "SQL",
				icon: <ApiOutlined />,
				onClick: () => navigate({ to: "/sql" }),
			},
		];

		// Build breadcrumbs from router matches
		const matches = useRouterState({ select: (s) => s.matches });

		const getBreadcrumbs = () => {
			const items: Array<{ title: string; href?: string }> = [];
			const path = location.pathname;

			// Always add Dashboard as root
			if (path !== "/") {
				items.push({ title: "Dashboard", href: "/" });
			} else {
				items.push({ title: "Dashboard" });
			}

			console.log("Current pathname:", path);
			console.log(
				"Current matches:",
				JSON.stringify(
					matches.map((m) => ({
						pathname: m.pathname,
						id: m.id,
						routeId: m.routeId,
						staticData: (m as any).staticData,
					})),
					null,
					2,
				),
			);
			console.log("Matches length:", matches.length);

			// Process matches to build breadcrumb trail
			matches.forEach((match) => {
				// Skip the root match
				if (match.pathname === "/") return;

				// Get breadcrumb from route's static data
				const staticData = (match as any).staticData;
				const breadcrumb = staticData?.breadcrumb;

				// Normalize pathname by removing trailing slash
				const normalizedPath = match.pathname.replace(/\/$/, "");

				// Handle service routes
				if (normalizedPath.match(/^\/service\/\d+$/)) {
					const portMatch = normalizedPath.match(/\/service\/(\d+)$/);
					if (portMatch) {
						const port = portMatch[1];
						const service = data?.services?.find(
							(s) => s.port === parseInt(port),
						);
						if (service) {
							items.push({
								title: `${service.name.substring(0, 4).toUpperCase()}:${service.port}`,
								href: normalizedPath,
							});
						}
					}
				}
				// Handle stats pages
				else if (breadcrumb && normalizedPath.match(/^\/service\/\d+\/.+$/)) {
					const servicePortMatch = match.pathname.match(/\/service\/(\d+)\/.+/);
					if (servicePortMatch) {
						const port = servicePortMatch[1];
						const service = data?.services?.find(
							(s) => s.port === parseInt(port),
						);
						if (
							service &&
							!items.some((item) => item.href === `/service/${port}`)
						) {
							items.push({
								title: `${service.name.substring(0, 4).toUpperCase()}:${service.port}`,
								href: `/service/${port}`,
							});
						}
					}
					// Add the actual breadcrumb for stats pages
					items.push({ title: breadcrumb });
				}
				// Handle dynamic routes like request/:id and tcp-connection/:id
				else if (match.pathname.includes("/request/")) {
					const requestMatch = match.pathname.match(
						/\/service\/(\d+)\/request\/(\d+)/,
					);
					if (requestMatch) {
						const port = requestMatch[1];
						const requestId = requestMatch[2];
						const service = data?.services?.find(
							(s) => s.port === parseInt(port),
						);
						if (
							service &&
							!items.some((item) => item.href === `/service/${port}`)
						) {
							items.push({
								title: `${service.name.substring(0, 4).toUpperCase()}:${service.port}`,
								href: `/service/${port}`,
							});
						}
						items.push({ title: `Request #${requestId}` });
					}
				} else if (match.pathname.includes("/tcp-connection/")) {
					const tcpMatch = match.pathname.match(
						/\/service\/(\d+)\/tcp-connection\/(\d+)/,
					);
					if (tcpMatch) {
						const port = tcpMatch[1];
						const connId = tcpMatch[2];
						const service = data?.services?.find(
							(s) => s.port === parseInt(port),
						);
						if (
							service &&
							!items.some((item) => item.href === `/service/${port}`)
						) {
							items.push({
								title: `${service.name.substring(0, 4).toUpperCase()}:${service.port}`,
								href: `/service/${port}`,
							});
						}
						items.push({ title: `TCP Connection #${connId}` });
					}
				}
				// Handle SQL route
				else if (match.pathname === "/sql" && breadcrumb) {
					items.push({ title: breadcrumb });
				}
			});

			return items;
		};

		if (isChecking) {
			return (
				<div
					style={{
						height: "100vh",
						display: "flex",
						alignItems: "center",
						justifyContent: "center",
					}}
				>
					<Spin size="large" tip="Checking server connection..." />
				</div>
			);
		}

		if (!isHealthy) {
			return <HostConfig visible={true} currentUrl={apiUrl} error={error} />;
		}

		return (
			<>
				<Layout style={{ minHeight: "100vh" }}>
					<Header style={{ display: "flex", alignItems: "center" }}>
						<div className="demo-logo" />
						<Menu
							theme="dark"
							mode="horizontal"
							selectedKeys={[getSelectedKey()]}
							items={menuItems}
							style={{ flex: 1, minWidth: 0 }}
						/>
						<Button
							type="text"
							icon={<SettingOutlined />}
							onClick={() => setSettingsOpen(true)}
							style={{ color: "white" }}
						>
							Settings
						</Button>
					</Header>
					<Content style={{ padding: "0 48px" }}>
						<div
							style={{
								margin: "16px 0",
								display: "flex",
								justifyContent: "space-between",
								alignItems: "center",
								minHeight: "32px",
							}}
						>
							<Breadcrumb
								items={getBreadcrumbs()}
								itemRender={(item, _, items) => {
									const last = items[items.length - 1];
									if (item === last) {
										return <span>{item.title}</span>;
									}
									return (
										<a onClick={() => item.href && navigate({ to: item.href })}>
											{item.title}
										</a>
									);
								}}
							/>
							<div id="page-actions" style={{ minHeight: "32px" }} />
						</div>
						<div
							style={{
								background: colorBgContainer,
								minHeight: "100%",
								padding: 24,
								borderRadius: borderRadiusLG,
							}}
						>
							<Outlet />
						</div>
					</Content>
					<Footer style={{ textAlign: "center" }}></Footer>
				</Layout>
				<TanstackDevtools
					config={{
						position: "bottom-left",
					}}
					plugins={[
						{
							name: "Tanstack Router",
							render: <TanStackRouterDevtoolsPanel />,
						},
						TanStackQueryDevtools,
					]}
				/>
				<SettingsModal
					open={settingsOpen}
					onClose={() => setSettingsOpen(false)}
				/>
			</>
		);
	},
});
