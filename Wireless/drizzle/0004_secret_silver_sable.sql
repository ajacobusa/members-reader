CREATE TABLE "circuits" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"property_id" uuid NOT NULL,
	"vendor_id" uuid,
	"circuit_ref" text NOT NULL,
	"type" text,
	"bandwidth_mbps" integer,
	"status" "device_status" DEFAULT 'online' NOT NULL,
	"monthly_cost" integer,
	"contract_end" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "project_checklist" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"project_id" uuid NOT NULL,
	"phase" text DEFAULT 'cutover' NOT NULL,
	"label" text NOT NULL,
	"done" integer DEFAULT 0 NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE TABLE "project_milestones" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"project_id" uuid NOT NULL,
	"name" text NOT NULL,
	"due_date" timestamp with time zone,
	"completed_at" timestamp with time zone,
	"sort_order" integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
ALTER TABLE "vendors" ADD COLUMN "contract_start" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "vendors" ADD COLUMN "contract_end" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "vendors" ADD COLUMN "sla_terms" text;--> statement-breakpoint
ALTER TABLE "circuits" ADD CONSTRAINT "circuits_property_id_properties_id_fk" FOREIGN KEY ("property_id") REFERENCES "public"."properties"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "circuits" ADD CONSTRAINT "circuits_vendor_id_vendors_id_fk" FOREIGN KEY ("vendor_id") REFERENCES "public"."vendors"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "project_checklist" ADD CONSTRAINT "project_checklist_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "project_milestones" ADD CONSTRAINT "project_milestones_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "circuits_property_idx" ON "circuits" USING btree ("property_id");--> statement-breakpoint
CREATE INDEX "project_checklist_project_idx" ON "project_checklist" USING btree ("project_id");--> statement-breakpoint
CREATE INDEX "project_milestones_project_idx" ON "project_milestones" USING btree ("project_id");