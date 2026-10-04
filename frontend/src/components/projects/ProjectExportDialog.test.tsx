// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectExportDialog } from "./ProjectExportDialog";
import type { ProjectSettings } from "@/types/projects";

describe("archive bundle export", () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
    HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  });
  it("keeps original inclusion opt-in and applies it only to bundles", () => {
    const download = vi.fn();
    render(<ProjectExportDialog settings={{format: "png", quality: 85, include_gps: false, organize_folders: false, master_format: null, manifest_format: null} as ProjectSettings} count={1} busy={false} onChange={vi.fn()} onDownload={download} onDeliver={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", {name: "Download ZIP"}));
    expect(download).toHaveBeenLastCalledWith(false, false);
    fireEvent.click(screen.getByLabelText(/Archive bundle/));
    expect((screen.getByLabelText("Include untouched originals") as HTMLInputElement).checked).toBe(false);
    expect((screen.getByRole("button", {name: "Folder or photo library"}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("Include untouched originals"));
    fireEvent.click(screen.getByRole("button", {name: "Download ZIP"}));
    expect(download).toHaveBeenLastCalledWith(true, true);
    fireEvent.click(screen.getByLabelText(/Archive bundle/));
    fireEvent.click(screen.getByRole("button", {name: "Download ZIP"}));
    expect(download).toHaveBeenLastCalledWith(false, false);
  });
});
