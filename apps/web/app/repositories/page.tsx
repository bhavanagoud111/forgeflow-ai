import type { Metadata } from "next";
import { RepositoriesList } from "@/components/repositories/repositories-list";

export const metadata: Metadata = { title: "Repositories" };

export default function RepositoriesPage() {
  return <RepositoriesList />;
}
