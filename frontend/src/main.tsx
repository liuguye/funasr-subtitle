import React from "react";
import ReactDOM from "react-dom/client";
import { App as AntApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import "@fontsource/space-mono/400.css";
import "@fontsource/space-mono/700.css";
import "./studio.css";
import "./studio/studio-layout.css";
import StudioPage from "./studio/StudioPage";
import { studioTheme } from "./theme";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider theme={studioTheme} locale={zhCN}>
      <AntApp>
        <StudioPage />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);
