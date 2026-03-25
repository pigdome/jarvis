DROP TABLE IF EXISTS `biblioimages`; 
CREATE TABLE `biblioimages` ( -- local cover images
 `imagenumber` int(11) NOT NULL AUTO_INCREMENT, -- unique identifier for the image
 `biblionumber` int(11) NOT NULL, -- foreign key from biblio table to link to biblionumber
 `mimetype` varchar(15) NOT NULL, -- image type
 `imagefile` mediumblob NOT NULL, -- image file contents
 `thumbnail` mediumblob NOT NULL, -- thumbnail file contents
 `timestamp` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, -- image creation/update time
 PRIMARY KEY (`imagenumber`),    
 CONSTRAINT `bibliocoverimage_fk1` FOREIGN KEY (`biblionumber`) REFERENCES `biblio` (`biblionumber`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `patronimage`; 
CREATE TABLE `patronimage` ( -- information related to patron images
  `borrowernumber` int(11) NOT NULL, -- the borrowernumber of the patron this image is attached to (borrowers.borrowernumber)
  `mimetype` varchar(15) NOT NULL, -- the format of the image (png, jpg, etc)
  `imagefile` mediumblob NOT NULL, -- the image
  PRIMARY KEY  (`borrowernumber`),
  CONSTRAINT `patronimage_fk1` FOREIGN KEY (`borrowernumber`) REFERENCES `borrowers` (`borrowernumber`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `action_logs`;
CREATE TABLE `action_logs` ( -- logs of actions taken in Koha (requires that the logs be turned on)
  `action_id` int(11) NOT NULL auto_increment, -- unique identifier for each action
  `timestamp` timestamp NOT NULL default CURRENT_TIMESTAMP, -- the date and time the action took place
  `user` int(11) NOT NULL default 0, -- the staff member who performed the action (borrowers.borrowernumber)
  `module` MEDIUMTEXT, -- the module this action was taken against
  `action` MEDIUMTEXT, -- the action (includes things like DELETED, ADDED, MODIFY, etc)
  `object` int(11) default NULL, -- the object that the action was taken against (could be a borrowernumber, itemnumber, etc)
  `info` MEDIUMTEXT, -- information about the action (usually includes SQL statement)
  `interface` VARCHAR(30) DEFAULT NULL, -- the context this action was taken in
  PRIMARY KEY (`action_id`),
  KEY `timestamp_idx` (`timestamp`),  
  KEY `user_idx` (`user`),   
  KEY `module_idx` (`module`(255)),
  KEY `action_idx` (`action`(255)),
  KEY `object_idx` (`object`),
  KEY `info_idx` (`info`(255)),
  KEY `interface` (`interface`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


DROP TABLE IF EXISTS `misc_files`;
CREATE TABLE IF NOT EXISTS `misc_files` ( -- miscellaneous files attached to records from various tables
  `file_id` int(11) NOT NULL AUTO_INCREMENT, -- unique id for the file record
  `table_tag` varchar(255) NOT NULL, -- usually table name, or arbitrary unique tag
  `record_id` int(11) NOT NULL, -- record id from the table this file is associated to
  `file_name` varchar(255) NOT NULL, -- file name
  `file_type` varchar(255) NOT NULL, -- MIME type of the file
  `file_description` varchar(255) DEFAULT NULL, -- description given to the file
  `file_content` longblob NOT NULL, -- file content
  `date_uploaded` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP, -- date and time the file was added
  PRIMARY KEY (`file_id`),  
  KEY `table_tag` (`table_tag`),    
  KEY `record_id` (`record_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
