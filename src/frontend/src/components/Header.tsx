import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "antd";
import { SettingOutlined } from "@ant-design/icons";
import SettingsModal from "./SettingsModal";

export default function Header() {
	const [settingsOpen, setSettingsOpen] = useState(false);

	return (
		<>
			<header className="p-2 flex gap-2 bg-white text-black justify-between">
				<nav className="flex flex-row">
					<div className="px-2 font-bold">
						<Link to="/">Home</Link>
					</div>

					<div className="px-2 font-bold">
						<Link to="/demo/tanstack-query">TanStack Query</Link>
					</div>
				</nav>

				<div>
					<Button
						icon={<SettingOutlined />}
						onClick={() => setSettingsOpen(true)}
					>
						Settings
					</Button>
				</div>
			</header>

			<SettingsModal
				open={settingsOpen}
				onClose={() => setSettingsOpen(false)}
			/>
		</>
	);
}
